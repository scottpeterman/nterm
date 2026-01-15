"""
nterm/scripting/api.py

Scripting API for nterm - usable from IPython, CLI, or MCP tools.
"""

from __future__ import annotations
import re
import time
import fnmatch
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass, asdict, field
from datetime import datetime

import paramiko

from ..manager.models import SessionStore, SavedSession, SessionFolder
from ..vault.resolver import CredentialResolver
from ..vault.store import StoredCredential
from ..connection.profile import ConnectionProfile, AuthMethod

# Reuse SSHSession's algorithm configuration
from ..session.ssh import (
    _apply_global_transport_settings,
    RSA_SHA1_DISABLED_ALGORITHMS,
)

# TextFSM parsing - REQUIRED
try:
    from nterm.parser.tfsm_fire import TextFSMAutoEngine
    TFSM_AVAILABLE = True
except ImportError as e:
    TFSM_AVAILABLE = False
    TextFSMAutoEngine = None
    _TFSM_IMPORT_ERROR = str(e)


# =============================================================================
# Platform Detection
# =============================================================================

PLATFORM_PATTERNS = {
    'arista_eos': [
        r'Arista',
        r'vEOS',
    ],
    'cisco_ios': [
        r'Cisco IOS Software',
        r'IOS \(tm\)',
    ],
    'cisco_nxos': [
        r'Cisco Nexus',
        r'NX-OS',
    ],
    'cisco_iosxe': [
        r'Cisco IOS XE Software',
    ],
    'cisco_iosxr': [
        r'Cisco IOS XR Software',
    ],
    'juniper_junos': [
        r'JUNOS',
        r'Juniper Networks',
    ],
}


# =============================================================================
# Platform-specific command mappings
# =============================================================================

PLATFORM_COMMANDS = {
    'arista_eos': {
        'interfaces_status': 'show interfaces status',
        'interface_detail': 'show interfaces {name}',
    },
    'cisco_ios': {
        'interfaces_status': 'show interfaces status',
        'interface_detail': 'show interfaces {name}',
    },
    'cisco_nxos': {
        'interfaces_status': 'show interface status',
        'interface_detail': 'show interface {name}',
    },
    'juniper_junos': {
        'interfaces_status': 'show interfaces terse',
        'interface_detail': 'show interfaces {name} extensive',
    },
}

DEFAULT_COMMANDS = {
    'interfaces_status': 'show interfaces status',
    'interface_detail': 'show interfaces {name}',
}


# =============================================================================
# Vendor Field Mappings for output normalization
# =============================================================================

# Maps canonical field names to vendor-specific template field names
INTERFACE_DETAIL_FIELD_MAP = {
    'arista_eos': {
        'interface': ['INTERFACE'],
        'admin_state': ['LINK_STATUS'],
        'oper_state': ['PROTOCOL_STATUS'],
        'hardware': ['HARDWARE_TYPE'],
        'mac_address': ['MAC_ADDRESS'],
        'description': ['DESCRIPTION'],
        'mtu': ['MTU'],
        'bandwidth': ['BANDWIDTH'],
        'in_packets': ['INPUT_PACKETS'],
        'out_packets': ['OUTPUT_PACKETS'],
        'in_errors': ['INPUT_ERRORS'],
        'out_errors': ['OUTPUT_ERRORS'],
        'crc_errors': ['CRC'],
    },
    'cisco_ios': {
        'interface': ['INTERFACE'],
        'admin_state': ['LINK_STATUS'],
        'oper_state': ['PROTOCOL_STATUS'],
        'hardware': ['HARDWARE_TYPE'],
        'mac_address': ['MAC_ADDRESS'],
        'description': ['DESCRIPTION'],
        'mtu': ['MTU'],
        'bandwidth': ['BANDWIDTH'],
        'duplex': ['DUPLEX'],
        'speed': ['SPEED'],
        'in_packets': ['INPUT_PACKETS'],
        'out_packets': ['OUTPUT_PACKETS'],
        'in_errors': ['INPUT_ERRORS'],
        'out_errors': ['OUTPUT_ERRORS'],
        'crc_errors': ['CRC'],
    },
    'cisco_nxos': {
        'interface': ['INTERFACE'],
        'admin_state': ['ADMIN_STATE', 'LINK_STATUS'],
        'oper_state': ['OPER_STATE', 'PROTOCOL_STATUS'],
        'hardware': ['HARDWARE_TYPE'],
        'mac_address': ['MAC_ADDRESS', 'ADDRESS'],
        'description': ['DESCRIPTION'],
        'mtu': ['MTU'],
        'bandwidth': ['BANDWIDTH', 'BW'],
        'in_packets': ['IN_PKTS', 'INPUT_PACKETS'],
        'out_packets': ['OUT_PKTS', 'OUTPUT_PACKETS'],
        'in_errors': ['IN_ERRORS', 'INPUT_ERRORS'],
        'out_errors': ['OUT_ERRORS', 'OUTPUT_ERRORS'],
        'crc_errors': ['CRC', 'CRC_ERRORS'],
    },
    'juniper_junos': {
        'interface': ['INTERFACE'],
        'admin_state': ['ADMIN_STATE'],
        'oper_state': ['LINK_STATUS'],
        'hardware': ['HARDWARE_TYPE'],
        'mac_address': ['MAC_ADDRESS'],
        'description': ['DESCRIPTION'],
        'mtu': ['MTU'],
        'bandwidth': ['BANDWIDTH'],
        'in_packets': ['INPUT_PACKETS'],
        'out_packets': ['OUTPUT_PACKETS'],
        'in_errors': ['INPUT_ERRORS'],
        'out_errors': ['OUTPUT_ERRORS'],
        'crc_errors': ['CRC'],
    },
}

DEFAULT_FIELD_MAP = {
    'interface': ['INTERFACE', 'PORT', 'NAME'],
    'admin_state': ['ADMIN_STATE', 'LINK_STATUS', 'STATUS'],
    'oper_state': ['OPER_STATE', 'PROTOCOL_STATUS', 'LINE_STATUS'],
    'hardware': ['HARDWARE_TYPE', 'HARDWARE', 'MEDIA_TYPE', 'TYPE'],
    'mac_address': ['MAC_ADDRESS', 'ADDRESS', 'MAC'],
    'description': ['DESCRIPTION', 'NAME', 'DESC'],
    'mtu': ['MTU'],
    'bandwidth': ['BANDWIDTH', 'BW', 'SPEED'],
    'duplex': ['DUPLEX'],
    'speed': ['SPEED'],
    'in_packets': ['INPUT_PACKETS', 'IN_PKTS', 'IN_PACKETS'],
    'out_packets': ['OUTPUT_PACKETS', 'OUT_PKTS', 'OUT_PACKETS'],
    'in_errors': ['INPUT_ERRORS', 'IN_ERRORS'],
    'out_errors': ['OUTPUT_ERRORS', 'OUT_ERRORS'],
    'crc_errors': ['CRC', 'CRC_ERRORS'],
}


@dataclass
class ActiveSession:
    """Represents an active SSH connection to a device."""
    device_name: str
    hostname: str
    port: int
    platform: Optional[str] = None
    client: Optional[paramiko.SSHClient] = None
    shell: Optional[paramiko.Channel] = None
    prompt: Optional[str] = None
    connected_at: datetime = field(default_factory=datetime.now)

    def is_connected(self) -> bool:
        """Check if session is still active."""
        return self.client is not None and self.shell is not None and self.shell.active

    def __repr__(self) -> str:
        status = "connected" if self.is_connected() else "disconnected"
        platform = f", platform={self.platform}" if self.platform else ""
        return f"<ActiveSession {self.device_name}@{self.hostname}:{self.port} {status}{platform}>"

    def __str__(self) -> str:
        """Detailed string representation."""
        lines = [
            f"Active Session: {self.device_name}",
            f"  Host: {self.hostname}:{self.port}",
            f"  Status: {'connected' if self.is_connected() else 'disconnected'}",
        ]
        if self.platform:
            lines.append(f"  Platform: {self.platform}")
        if self.prompt:
            lines.append(f"  Prompt: {self.prompt}")
        lines.append(f"  Connected at: {self.connected_at.strftime('%Y-%m-%d %H:%M:%S')}")
        return '\n'.join(lines)


@dataclass
class CommandResult:
    """Result of executing a command on a device."""
    command: str
    raw_output: str
    platform: Optional[str] = None
    parsed_data: Optional[List[Dict[str, Any]]] = None
    parse_success: bool = False
    parse_template: Optional[str] = None
    normalized_fields: Optional[Dict[str, str]] = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'command': self.command,
            'raw_output': self.raw_output,
            'platform': self.platform,
            'parsed_data': self.parsed_data,
            'parse_success': self.parse_success,
            'parse_template': self.parse_template,
            'normalized_fields': self.normalized_fields,
            'timestamp': self.timestamp.isoformat(),
        }

    def __repr__(self) -> str:
        parsed = f", {len(self.parsed_data)} parsed" if self.parsed_data else ""
        platform = f", platform={self.platform}" if self.platform else ""
        return f"<CommandResult '{self.command}'{platform}{parsed}>"

    def __str__(self) -> str:
        """Detailed string representation."""
        lines = [
            f"Command: {self.command}",
            f"Timestamp: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
        ]
        if self.platform:
            lines.append(f"Platform: {self.platform}")

        lines.append(f"Parse success: {self.parse_success}")
        if self.parse_template:
            lines.append(f"Template: {self.parse_template}")

        if self.parsed_data:
            lines.append(f"Parsed rows: {len(self.parsed_data)}")
            if self.normalized_fields:
                lines.append(f"Field normalization: {self.normalized_fields['map_used']}")

        lines.append(f"\nRaw output ({len(self.raw_output)} chars):")
        lines.append("-" * 60)
        lines.append(self.raw_output[:500] + ("..." if len(self.raw_output) > 500 else ""))

        return '\n'.join(lines)


@dataclass
class DeviceInfo:
    """Simplified device view for scripting."""
    name: str
    hostname: str
    port: int
    folder: Optional[str] = None
    credential: Optional[str] = None
    last_connected: Optional[str] = None
    connect_count: int = 0

    @classmethod
    def from_session(cls, session: SavedSession, folder_name: str = None) -> 'DeviceInfo':
        return cls(
            name=session.name,
            hostname=session.hostname,
            port=session.port,
            folder=folder_name,
            credential=session.credential_name,
            last_connected=str(session.last_connected) if session.last_connected else None,
            connect_count=session.connect_count,
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def __repr__(self) -> str:
        cred = f", cred={self.credential}" if self.credential else ""
        folder = f", folder={self.folder}" if self.folder else ""
        return f"Device({self.name}, {self.hostname}:{self.port}{cred}{folder})"

    def __str__(self) -> str:
        """Detailed string representation."""
        lines = [
            f"Device: {self.name}",
            f"  Hostname: {self.hostname}:{self.port}",
        ]
        if self.folder:
            lines.append(f"  Folder: {self.folder}")
        if self.credential:
            lines.append(f"  Credential: {self.credential}")
        if self.last_connected:
            lines.append(f"  Last connected: {self.last_connected}")
        if self.connect_count > 0:
            lines.append(f"  Connection count: {self.connect_count}")
        return '\n'.join(lines)


@dataclass
class CredentialInfo:
    """Simplified credential view for scripting (no secrets exposed)."""
    name: str
    username: str
    has_password: bool
    has_key: bool
    match_hosts: List[str]
    match_tags: List[str]
    jump_host: Optional[str] = None
    is_default: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def __repr__(self) -> str:
        auth = []
        if self.has_password:
            auth.append("password")
        if self.has_key:
            auth.append("key")
        auth_str = "+".join(auth) if auth else "none"
        default = " [default]" if self.is_default else ""
        return f"Credential({self.name}, user={self.username}, auth={auth_str}{default})"

    def __str__(self) -> str:
        """Detailed string representation."""
        lines = [
            f"Credential: {self.name}",
            f"  Username: {self.username}",
            f"  Authentication: {'password' if self.has_password else ''}{'+' if self.has_password and self.has_key else ''}{'SSH key' if self.has_key else ''}",
        ]
        if self.match_hosts:
            lines.append(f"  Host patterns: {', '.join(self.match_hosts)}")
        if self.match_tags:
            lines.append(f"  Tags: {', '.join(self.match_tags)}")
        if self.jump_host:
            lines.append(f"  Jump host: {self.jump_host}")
        if self.is_default:
            lines.append(f"  [DEFAULT]")
        return '\n'.join(lines)


class NTermAPI:
    """
    Scripting interface for nterm.

    Provides read access to saved sessions and credentials,
    and connection/command execution capabilities.

    Usage:
        api = NTermAPI()

        # List and search devices
        api.devices()
        api.search("leaf")
        api.devices("Lab-*")

        # Credentials (requires unlocked vault)
        api.credentials()
        api.credential("lab-admin")

        # Connect and execute (future)
        session = api.connect("eng-leaf-1")
        output = api.send(session, "show version")
    """

    def __init__(
        self,
        session_store: SessionStore = None,
        credential_resolver: CredentialResolver = None,
        tfsm_db_path: str = None,
    ):
        self._sessions = session_store or SessionStore()
        self._resolver = credential_resolver or CredentialResolver()
        self._folder_cache: Dict[int, str] = {}
        self._active_sessions: Dict[str, ActiveSession] = {}

        # Initialize TextFSM engine - REQUIRED for command parsing
        if not TFSM_AVAILABLE:
            error_msg = (
                "TextFSM parser not available. "
                "Ensure tfsm_fire.py is in nterm/parser/\n"
            )
            if '_TFSM_IMPORT_ERROR' in globals():
                error_msg += f"Import error: {_TFSM_IMPORT_ERROR}"
            raise RuntimeError(error_msg)

        try:
            # Default to looking for tfsm_templates.db in current directory
            if not tfsm_db_path:
                tfsm_db_path = "./tfsm_templates.db"
            elif tfsm_db_path == "./":
                tfsm_db_path = "./tfsm_templates.db"

            self._tfsm_engine = TextFSMAutoEngine(db_path=tfsm_db_path)
            if not self._tfsm_engine or not self._tfsm_engine.db_path:
                raise RuntimeError("TextFSM engine initialized but no database path")
        except Exception as e:
            raise RuntimeError(
                f"Failed to initialize TextFSM engine: {e}\n"
                f"Expected database at: {tfsm_db_path or 'default location'}\n"
                "The API requires tfsm_templates.db for command parsing."
            )

    # -------------------------------------------------------------------------
    # Device / Session listing
    # -------------------------------------------------------------------------

    def devices(self, pattern: str = None, folder: str = None) -> List[DeviceInfo]:
        """
        List saved devices/sessions.

        Args:
            pattern: Optional glob pattern to filter by name (e.g., "eng-*", "*leaf*")
            folder: Optional folder name to filter by

        Returns:
            List of DeviceInfo objects

        Examples:
            api.devices()                  # All devices
            api.devices("eng-*")           # All devices starting with "eng-"
            api.devices(folder="Lab-ENG")  # All devices in Lab-ENG folder
        """
        self._refresh_folder_cache()
        sessions = self._sessions.list_all_sessions()

        results = []
        for session in sessions:
            folder_name = self._folder_cache.get(session.folder_id)

            # Filter by folder if specified
            if folder and folder_name != folder:
                continue

            # Filter by pattern if specified
            if pattern and not fnmatch.fnmatch(session.name, pattern):
                continue

            results.append(DeviceInfo.from_session(session, folder_name))

        return results

    def search(self, query: str) -> List[DeviceInfo]:
        """
        Search devices by name, hostname, or description.

        Args:
            query: Search string (partial match)

        Returns:
            List of matching DeviceInfo objects

        Examples:
            api.search("leaf")        # Find devices with "leaf" in name/hostname
            api.search("192.168")     # Find devices by IP prefix
        """
        self._refresh_folder_cache()
        sessions = self._sessions.search_sessions(query)

        return [
            DeviceInfo.from_session(s, self._folder_cache.get(s.folder_id))
            for s in sessions
        ]

    def device(self, name: str) -> Optional[DeviceInfo]:
        """
        Get a specific device by exact name.

        Args:
            name: Device/session name

        Returns:
            DeviceInfo or None if not found

        Examples:
            api.device("eng-leaf-1")
        """
        self._refresh_folder_cache()
        sessions = self._sessions.list_all_sessions()

        for session in sessions:
            if session.name == name:
                return DeviceInfo.from_session(
                    session,
                    self._folder_cache.get(session.folder_id)
                )
        return None

    def folders(self) -> List[str]:
        """
        List all folder names.

        Returns:
            List of folder names
        """
        self._refresh_folder_cache()
        return list(self._folder_cache.values())

    def _refresh_folder_cache(self):
        """Refresh folder ID -> name mapping."""
        tree = self._sessions.get_tree()
        self._folder_cache = {f.id: f.name for f in tree["folders"]}

    # -------------------------------------------------------------------------
    # Credential access
    # -------------------------------------------------------------------------

    @property
    def vault_unlocked(self) -> bool:
        """Check if credential vault is unlocked."""
        return self._resolver.store.is_unlocked if self._resolver.is_initialized() else False

    @property
    def vault_initialized(self) -> bool:
        """Check if vault exists."""
        return self._resolver.is_initialized()

    def unlock(self, password: str) -> bool:
        """
        Unlock the credential vault.

        Args:
            password: Vault master password

        Returns:
            True if unlocked successfully
        """
        return self._resolver.unlock_vault(password)

    def lock(self) -> None:
        """Lock the credential vault."""
        self._resolver.lock_vault()

    def credentials(self, pattern: str = None) -> List[CredentialInfo]:
        """
        List available credentials (names and metadata only, no secrets).

        Args:
            pattern: Optional glob pattern to filter by name

        Returns:
            List of CredentialInfo objects

        Raises:
            RuntimeError: If vault is locked

        Examples:
            api.credentials()              # All credentials
            api.credentials("*admin*")     # Credentials with "admin" in name
        """
        if not self.vault_unlocked:
            raise RuntimeError("Vault is locked. Call api.unlock(password) first.")

        creds = self._resolver.list_credentials()
        results = []

        for cred in creds:
            if pattern and not fnmatch.fnmatch(cred.name, pattern):
                continue

            results.append(CredentialInfo(
                name=cred.name,
                username=cred.username,
                has_password=bool(cred.password),
                has_key=bool(cred.ssh_key),
                match_hosts=cred.match_hosts or [],
                match_tags=cred.match_tags or [],
                jump_host=cred.jump_host,
                is_default=cred.is_default,
            ))

        return results

    def credential(self, name: str) -> Optional[CredentialInfo]:
        """
        Get credential info by name (no secrets exposed).

        Args:
            name: Credential name

        Returns:
            CredentialInfo or None

        Raises:
            RuntimeError: If vault is locked
        """
        if not self.vault_unlocked:
            raise RuntimeError("Vault is locked. Call api.unlock(password) first.")

        cred = self._resolver.get_credential(name)
        if not cred:
            return None

        return CredentialInfo(
            name=cred.name,
            username=cred.username,
            has_password=bool(cred.password),
            has_key=bool(cred.ssh_key),
            match_hosts=cred.match_hosts or [],
            match_tags=cred.match_tags or [],
            jump_host=cred.jump_host,
            is_default=cred.is_default,
        )

    def resolve_credential(self, hostname: str, tags: List[str] = None) -> Optional[str]:
        """
        Find which credential would be used for a hostname.

        Args:
            hostname: Target hostname
            tags: Optional device tags

        Returns:
            Credential name that would match, or None

        Raises:
            RuntimeError: If vault is locked
        """
        if not self.vault_unlocked:
            raise RuntimeError("Vault is locked.")

        try:
            profile = self._resolver.resolve_for_device(hostname, tags)
            # Extract credential name from profile name format "hostname (cred_name)"
            if "(" in profile.name and ")" in profile.name:
                return profile.name.split("(")[1].rstrip(")")
            return None
        except Exception:
            return None

    # -------------------------------------------------------------------------
    # Connection operations
    # -------------------------------------------------------------------------

    def _detect_platform(self, version_output: str) -> Optional[str]:
        """Detect device platform from 'show version' output."""
        for platform, patterns in PLATFORM_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, version_output, re.IGNORECASE):
                    return platform
        return None

    def _normalize_fields(
        self,
        parsed_data: List[Dict[str, Any]],
        platform: str,
        field_map_dict: Dict[str, Dict[str, List[str]]],
    ) -> List[Dict[str, Any]]:
        """
        Normalize vendor-specific field names to canonical names.

        Args:
            parsed_data: Raw parsed data from TextFSM
            platform: Detected platform
            field_map_dict: Mapping dict (e.g., INTERFACE_DETAIL_FIELD_MAP)

        Returns:
            List of dicts with normalized field names
        """
        field_map = field_map_dict.get(platform, DEFAULT_FIELD_MAP)
        normalized = []

        for row in parsed_data:
            norm_row = {}
            for canonical_name, vendor_names in field_map.items():
                for vendor_name in vendor_names:
                    if vendor_name in row:
                        norm_row[canonical_name] = row[vendor_name]
                        break
            # Keep any fields that weren't in the mapping
            for key, value in row.items():
                if key not in [vn for vnames in field_map.values() for vn in vnames]:
                    norm_row[key] = value
            normalized.append(norm_row)

        return normalized

    def _wait_for_prompt(
        self,
        shell: paramiko.Channel,
        timeout: int = 10,
        initial_wait: float = 0.5,
    ) -> str:
        """
        Wait for device prompt and return detected prompt pattern.

        Returns:
            Detected prompt string
        """
        time.sleep(initial_wait)

        # Send newline to trigger prompt
        shell.send('\n')
        time.sleep(0.3)

        output = ""
        end_time = time.time() + timeout

        while time.time() < end_time:
            if shell.recv_ready():
                chunk = shell.recv(4096).decode('utf-8', errors='ignore')
                output += chunk
                time.sleep(0.1)
            else:
                break

        # Extract last line as prompt (after last newline)
        lines = output.strip().split('\n')
        prompt = lines[-1] if lines else ""

        # Common prompt patterns: ends with #, >, $
        if prompt and prompt[-1] in '#>$':
            return prompt

        return prompt

    def _send_command(
        self,
        shell: paramiko.Channel,
        command: str,
        prompt: str,
        timeout: int = 30,
    ) -> str:
        """
        Send command and collect output until prompt returns.

        Args:
            shell: Active SSH channel
            command: Command to execute
            prompt: Expected prompt pattern
            timeout: Command timeout in seconds

        Returns:
            Command output (without echoed command and prompt)
        """
        # Clear any pending input aggressively
        time.sleep(0.1)
        while shell.recv_ready():
            shell.recv(65536)
            time.sleep(0.05)

        # Send command - strip whitespace to avoid issues
        command = command.strip()
        shell.send(command + '\n')
        time.sleep(0.3)  # Give device time to echo command

        output = ""
        end_time = time.time() + timeout
        prompt_seen = False

        # Paging prompts to handle (--More--, -- More --, etc.)
        paging_prompts = [
            '--More--',
            '-- More --',
            '<--- More --->',
            'Press any key to continue',
        ]

        while time.time() < end_time:
            if shell.recv_ready():
                chunk = shell.recv(65536).decode('utf-8', errors='ignore')
                output += chunk

                # Check for paging prompt
                for paging_prompt in paging_prompts:
                    if paging_prompt in output:
                        # Send space to continue
                        shell.send(' ')
                        time.sleep(0.2)
                        # Remove paging prompt from output
                        output = output.replace(paging_prompt, '')
                        break

                # Check if we've received the final prompt
                if prompt in output:
                    prompt_seen = True
                    # Give a bit more time for any trailing data
                    time.sleep(0.1)
                    if shell.recv_ready():
                        chunk = shell.recv(65536).decode('utf-8', errors='ignore')
                        output += chunk
                    break

                time.sleep(0.1)
            else:
                if prompt_seen or len(output) > 0:
                    time.sleep(0.3)
                    if not shell.recv_ready():
                        break

        # Clean up output: remove echoed command and prompt
        lines = output.split('\n')

        # Remove first line if it contains the echoed command
        if lines and command.lower() in lines[0].lower():
            lines = lines[1:]

        # Remove last line if it's the prompt
        if lines and prompt in lines[-1]:
            lines = lines[:-1]

        # Also remove any lines that are just the prompt or empty
        cleaned_lines = []
        for line in lines:
            stripped = line.strip('\r\n ')
            # Skip prompt lines and residual paging artifacts
            if stripped and stripped != prompt and not any(p in stripped for p in paging_prompts):
                cleaned_lines.append(line)

        return '\n'.join(cleaned_lines).strip()

    def connect(self, device: str, credential: str = None, debug: bool = False) -> ActiveSession:
        """
        Connect to a device and detect platform.

        Args:
            device: Device name (from saved sessions) or hostname
            credential: Optional credential name (auto-resolved if not specified)
            debug: Enable verbose connection debugging

        Returns:
            ActiveSession handle for sending commands
        """
        debug_log = []

        def _debug(msg):
            if debug:
                debug_log.append(msg)
                print(f"[DEBUG] {msg}")

        # Look up device from saved sessions first
        device_info = self.device(device)

        if device_info:
            hostname = device_info.hostname
            port = device_info.port
            device_name = device_info.name
            saved_cred = device_info.credential
        else:
            hostname = device
            port = 22
            device_name = device
            saved_cred = None

        _debug(f"Target: {hostname}:{port}")

        # Resolve credentials
        if not self.vault_unlocked:
            raise RuntimeError("Vault is locked. Call api.unlock(password) first.")

        cred_name = credential or saved_cred
        _debug(f"Credential: {cred_name or '(auto-resolve)'}")

        if cred_name:
            try:
                profile = self._resolver.create_profile_for_credential(
                    credential_name=cred_name,
                    hostname=hostname,
                    port=port,
                )
            except Exception as e:
                raise ValueError(f"Failed to get credential '{cred_name}': {e}")
        else:
            try:
                profile = self._resolver.resolve_for_device(hostname, port=port)
            except Exception as e:
                raise ValueError(f"Failed to resolve credentials for {hostname}: {e}")

        if not profile:
            raise ValueError(f"No credentials available for {hostname}")

        # Apply legacy algorithm support
        _apply_global_transport_settings()

        # Prepare connection kwargs
        connect_kwargs = {
            'hostname': hostname,
            'port': port,
            'timeout': 10,
            'allow_agent': False,
            'look_for_keys': False,
        }

        # Add authentication from profile
        auth_method_used = None
        if profile.auth_methods:
            first_auth = profile.auth_methods[0]
            connect_kwargs['username'] = first_auth.username
            _debug(f"Username: {first_auth.username}")

            for auth in profile.auth_methods:
                if auth.method == AuthMethod.PASSWORD:
                    connect_kwargs['password'] = auth.password
                    auth_method_used = "password"
                    _debug("Auth method: password")
                    break
                elif auth.method == AuthMethod.KEY_FILE:
                    connect_kwargs['key_filename'] = auth.key_path
                    if auth.key_passphrase:
                        connect_kwargs['passphrase'] = auth.key_passphrase
                    auth_method_used = f"key_file:{auth.key_path}"
                    _debug(f"Auth method: key_file ({auth.key_path})")
                    break
                elif auth.method == AuthMethod.KEY_STORED:
                    import tempfile
                    key_file = tempfile.NamedTemporaryFile(
                        mode='w',
                        delete=False,
                        suffix='.pem'
                    )
                    key_file.write(auth.key_data)
                    key_file.close()
                    connect_kwargs['key_filename'] = key_file.name
                    if auth.key_passphrase:
                        connect_kwargs['passphrase'] = auth.key_passphrase
                    auth_method_used = "key_stored"
                    _debug(f"Auth method: key_stored (temp: {key_file.name})")
                    break

        # Detect key type if using key auth
        if 'key_filename' in connect_kwargs:
            key_path = connect_kwargs['key_filename']
            key_type = "unknown"
            key_bits = None
            try:
                key = paramiko.RSAKey.from_private_key_file(key_path)
                key_type = "RSA"
                key_bits = key.get_bits()
            except:
                try:
                    key = paramiko.Ed25519Key.from_private_key_file(key_path)
                    key_type = "Ed25519"
                except:
                    try:
                        key = paramiko.ECDSAKey.from_private_key_file(key_path)
                        key_type = "ECDSA"
                    except:
                        pass
            _debug(f"Key type: {key_type}" + (f" ({key_bits} bits)" if key_bits else ""))

        # Connection attempt sequence
        attempts = [
            ("modern", None),
            ("rsa-sha1", RSA_SHA1_DISABLED_ALGORITHMS),
        ]

        last_error = None
        connected = False
        client = None

        for attempt_name, disabled_algs in attempts:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            _debug(f"Attempt: {attempt_name}")

            attempt_kwargs = connect_kwargs.copy()
            if disabled_algs:
                attempt_kwargs['disabled_algorithms'] = disabled_algs
                _debug(f"  disabled_algorithms: {disabled_algs}")

            try:
                client.connect(**attempt_kwargs)
                connected = True

                # Log successful negotiation
                transport = client.get_transport()
                if transport:
                    _debug(f"  SUCCESS - cipher: {transport.remote_cipher}, mac: {transport.remote_mac}")
                    _debug(f"  host_key_type: {transport.host_key_type}")
                break

            except paramiko.AuthenticationException as e:
                _debug(f"  FAILED (auth): {e}")
                last_error = str(e)
                client.close()
            except paramiko.SSHException as e:
                _debug(f"  FAILED (ssh): {e}")
                last_error = str(e)
                client.close()
            except Exception as e:
                _debug(f"  FAILED (other): {e}")
                last_error = str(e)
                client.close()

        if not connected:
            # Build detailed error message
            error_detail = f"Connection failed: {last_error}"
            if debug:
                error_detail += f"\n\nDebug log:\n" + "\n".join(debug_log)
            raise paramiko.AuthenticationException(error_detail)

        # Open interactive shell
        shell = client.invoke_shell(width=200, height=50)
        shell.settimeout(0.5)

        prompt = self._wait_for_prompt(shell)
        _debug(f"Prompt detected: {prompt}")

        session = ActiveSession(
            device_name=device_name,
            hostname=hostname,
            port=port,
            client=client,
            shell=shell,
            prompt=prompt,
        )

        # Detect platform
        try:
            version_output = self._send_command(shell, "show version", prompt)
            platform = self._detect_platform(version_output)
            session.platform = platform
            _debug(f"Platform detected: {platform}")
        except Exception as e:
            _debug(f"Platform detection failed: {e}")

        # Disable terminal paging
        try:
            if session.platform and 'cisco' in session.platform:
                self._send_command(shell, "terminal length 0", prompt, timeout=5)
            elif session.platform == 'juniper_junos':
                self._send_command(shell, "set cli screen-length 0", prompt, timeout=5)
            elif session.platform == 'arista_eos':
                self._send_command(shell, "terminal length 0", prompt, timeout=5)
        except Exception as e:
            _debug(f"Failed to disable paging: {e}")

        self._active_sessions[device_name] = session
        return session

    def send(
        self,
        session: ActiveSession,
        command: str,
        timeout: int = 30,
        parse: bool = True,
        normalize: bool = True,
    ) -> CommandResult:
        """
        Send command to a connected session.

        Args:
            session: ActiveSession from connect()
            command: Command to execute
            timeout: Command timeout in seconds
            parse: Whether to attempt TextFSM parsing
            normalize: Whether to normalize field names (requires parse=True)

        Returns:
            CommandResult with raw and parsed output

        Examples:
            result = api.send(session, "show version")
            result = api.send(session, "show interfaces status", parse=True)

            # Access results
            print(result.raw_output)
            if result.parsed_data:
                for row in result.parsed_data:
                    print(row)
        """
        if not session.is_connected():
            raise RuntimeError(f"Session {session.device_name} is not connected")

        # Execute command
        raw_output = self._send_command(session.shell, command, session.prompt, timeout)

        # Create result object
        result = CommandResult(
            command=command,
            raw_output=raw_output,
            platform=session.platform,
        )

        # Attempt parsing if requested and TextFSM available
        if parse:
            if not self._tfsm_engine:
                raise RuntimeError(
                    "TextFSM parser not initialized. Cannot parse command output. "
                    "This should not happen - API should have failed during initialization."
                )

            if not session.platform:
                # Can't parse without platform hint
                result.parse_success = False
            else:
                try:
                    # Convert command to filter string (e.g., "show version" -> "show_version")
                    filter_string = command.strip().replace(' ', '_')

                    # Call the actual tfsm_fire method
                    best_template, parsed_data, best_score, all_scores = self._tfsm_engine.find_best_template(
                        device_output=raw_output,
                        filter_string=filter_string,
                    )

                    if parsed_data and len(parsed_data) > 0:
                        result.parsed_data = parsed_data
                        result.parse_success = True
                        result.parse_template = best_template

                        # Normalize field names if requested
                        if normalize and parsed_data:
                            # Determine which field map to use based on command
                            if 'interface' in command.lower():
                                normalized = self._normalize_fields(
                                    parsed_data,
                                    session.platform,
                                    INTERFACE_DETAIL_FIELD_MAP,
                                )
                                result.parsed_data = normalized
                                result.normalized_fields = {
                                    'map_used': 'INTERFACE_DETAIL_FIELD_MAP',
                                    'platform': session.platform,
                                }
                    else:
                        # Parsing returned empty/None
                        result.parse_success = False

                except Exception as e:
                    # Parsing failed, but we still have raw output
                    result.parse_success = False

        return result

    def disconnect(self, session: ActiveSession) -> None:
        """
        Disconnect a session.

        Args:
            session: ActiveSession to close
        """
        if session.device_name in self._active_sessions:
            del self._active_sessions[session.device_name]

        if session.shell:
            session.shell.close()

        if session.client:
            session.client.close()

    def active_sessions(self) -> List[str]:
        """
        List currently active session names.

        Returns:
            List of device names with active connections
        """
        return list(self._active_sessions.keys())

    def db_info(self) -> Dict[str, Any]:
        """
        Get detailed information about TextFSM database.

        Returns:
            Dict with database path, existence, and diagnostic info
        """
        from pathlib import Path
        import os

        info = {
            "engine_available": self._tfsm_engine is not None,
            "db_path": None,
            "db_exists": False,
            "db_absolute_path": None,
            "current_working_directory": os.getcwd(),
        }

        if self._tfsm_engine and hasattr(self._tfsm_engine, 'db_path'):
            info["db_path"] = self._tfsm_engine.db_path

            if info["db_path"]:
                db_path = Path(info["db_path"])
                info["db_exists"] = db_path.exists()
                info["db_absolute_path"] = str(db_path.absolute())
                info["db_is_directory"] = db_path.is_dir() if db_path.exists() else None

                if info["db_exists"]:
                    if db_path.is_file():
                        info["db_size"] = db_path.stat().st_size
                        info["db_size_mb"] = round(db_path.stat().st_size / 1024 / 1024, 2)
                    else:
                        info["error"] = f"Path exists but is not a file: {db_path}"
                else:
                    # Try common locations
                    common_locations = [
                        Path(os.getcwd()) / "tfsm_templates.db",
                        Path.home() / ".nterm" / "tfsm_templates.db",
                        Path(__file__).parent.parent / "tfsm_templates.db",
                    ]
                    info["tried_locations"] = [str(p) for p in common_locations]
                    info["found_at"] = [str(p) for p in common_locations if p.exists()]

        return info

    def debug_parse(
        self,
        command: str,
        output: str,
        platform: str,
    ) -> Dict[str, Any]:
        """
        Debug TextFSM parsing - useful for troubleshooting why parsing fails.

        Args:
            command: Command that was executed
            output: Raw output from device
            platform: Platform hint (e.g., 'cisco_ios')

        Returns:
            Dict with parsing debug info including:
            - parsed_data: Parsed results if successful
            - template_used: Template file name if found
            - error: Error message if parsing failed
            - attempted_templates: List of templates attempted
        """
        if not self._tfsm_engine:
            return {"error": "TextFSM engine not initialized"}

        debug_info = {
            "command": command,
            "platform": platform,
            "output_length": len(output),
            "output_preview": output[:200] if output else None,
        }

        try:
            # Convert command to filter string
            filter_string = command.strip().replace(' ', '_')

            best_template, parsed_data, best_score, all_scores = self._tfsm_engine.find_best_template(
                device_output=output,
                filter_string=filter_string,
            )

            debug_info["parsed_data"] = parsed_data
            debug_info["parse_success"] = parsed_data is not None and len(parsed_data) > 0
            debug_info["template_used"] = best_template
            debug_info["best_score"] = best_score
            debug_info["all_scores"] = all_scores  # List of (template_name, score, record_count)

            if parsed_data:
                debug_info["row_count"] = len(parsed_data)
                if parsed_data:
                    debug_info["sample_row"] = parsed_data[0]
            else:
                debug_info["error"] = "Parsing returned None or empty"

        except Exception as e:
            debug_info["error"] = str(e)
            debug_info["parse_success"] = False

        return debug_info

    # -------------------------------------------------------------------------
    # Convenience / REPL helpers
    # -------------------------------------------------------------------------

    def __repr__(self) -> str:
        device_count = len(self._sessions.list_all_sessions())
        vault_status = "unlocked" if self.vault_unlocked else "locked"
        parser_status = "enabled" if self._tfsm_engine else "disabled"
        active = len(self._active_sessions)
        return f"<NTermAPI: {device_count} devices, vault {vault_status}, parser {parser_status}, {active} active>"

    def status(self) -> Dict[str, Any]:
        """
        Get API status summary.

        Returns:
            Dict with device count, folder count, credential count, vault status, parser status
        """
        sessions = self._sessions.list_all_sessions()
        folders = self._sessions.get_tree()["folders"]

        cred_count = 0
        if self.vault_unlocked:
            cred_count = len(self._resolver.list_credentials())

        # Check parser DB status
        parser_db_path = None
        parser_db_exists = False
        if self._tfsm_engine and hasattr(self._tfsm_engine, 'db_path'):
            parser_db_path = self._tfsm_engine.db_path
            if parser_db_path:
                from pathlib import Path
                parser_db_exists = Path(parser_db_path).exists()

        return {
            "devices": len(sessions),
            "folders": len(folders),
            "credentials": cred_count,
            "vault_initialized": self.vault_initialized,
            "vault_unlocked": self.vault_unlocked,
            "active_sessions": len(self._active_sessions),
            "parser_available": self._tfsm_engine is not None,
            "parser_db": parser_db_path,
            "parser_db_exists": parser_db_exists,
        }

    def help(self) -> None:
        """Print available commands."""
        print("""
nterm API Commands
==================

Devices:
  api.devices()                    List all devices
  api.devices("pattern*")          Filter by glob pattern
  api.devices(folder="Lab-ENG")    Filter by folder
  api.search("query")              Search by name/hostname/description
  api.device("name")               Get specific device
  api.folders()                    List all folders

Credentials (requires unlocked vault):
  api.unlock("password")           Unlock vault
  api.lock()                       Lock vault
  api.credentials()                List all credentials
  api.credentials("*admin*")       Filter by pattern
  api.credential("name")           Get specific credential
  api.resolve_credential("host")   Find matching credential

Connections:
  session = api.connect("device")  Connect to device (auto-detect platform)
  result = api.send(session, cmd)  Execute command (returns CommandResult)
  api.disconnect(session)          Close connection
  api.active_sessions()            List active connections

Command Results:
  result.raw_output                Raw text from device
  result.parsed_data               Parsed data (List[Dict]) if available
  result.platform                  Detected platform
  result.parse_success             Whether parsing succeeded
  result.to_dict()                 Export as dictionary

Debugging:
  api.debug_parse(cmd, output, platform)  Debug why parsing failed
  api.db_info()                    Show TextFSM database path and status
  
Status:
  api.status()                     Get summary
  api.vault_unlocked               Check vault status
  api._tfsm_engine                 TextFSM parser (required)

Examples:
  # Connect and execute
  api.unlock("vault-password")
  session = api.connect("spine1")
  result = api.send(session, "show interfaces status")
  
  # Access parsed data
  if result.parsed_data:
      for interface in result.parsed_data:
          print(f"{interface['name']}: {interface['status']}")
  
  # Disconnect
  api.disconnect(session)

Note: TextFSM parser (tfsm_templates.db) is REQUIRED for the API to function.
The API will fail during initialization if the database is not found.
""")


# Singleton for convenience in IPython
_default_api: Optional[NTermAPI] = None

def get_api() -> NTermAPI:
    """Get or create default API instance."""
    global _default_api
    if _default_api is None:
        _default_api = NTermAPI()
    return _default_api


def reset_api() -> NTermAPI:
    """Reset and return fresh API instance."""
    global _default_api
    _default_api = NTermAPI()
    return _default_api