"""
nterm/scripting/api.py

Scripting API for nterm - usable from IPython, CLI, or MCP tools.
"""

from __future__ import annotations
import fnmatch
from contextlib import contextmanager
from typing import Optional, List, Dict, Any, Generator
from pathlib import Path
import os

from ..manager.models import SessionStore
from ..vault.resolver import CredentialResolver

# Import our refactored modules
from .models import ActiveSession, CommandResult, DeviceInfo, CredentialInfo
from .platform_data import INTERFACE_DETAIL_FIELD_MAP
from .platform_utils import (
    detect_platform,
    normalize_fields,
    get_paging_disable_command,
    get_platform_command,
    extract_version_info,
    extract_neighbor_info,
)
from .ssh_connection import connect_ssh, send_command

# TextFSM parsing - REQUIRED
try:
    from nterm.parser.tfsm_fire import TextFSMAutoEngine
    TFSM_AVAILABLE = True
except ImportError as e:
    TFSM_AVAILABLE = False
    TextFSMAutoEngine = None
    _TFSM_IMPORT_ERROR = str(e)


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

        # Connect and execute
        session = api.connect("eng-leaf-1")
        output = api.send(session, "show version")

        # Context manager (auto-cleanup)
        with api.session("eng-leaf-1") as s:
            result = api.send(s, "show version")
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

        # Resolve credentials
        if not self.vault_unlocked:
            raise RuntimeError("Vault is locked. Call api.unlock(password) first.")

        cred_name = credential or saved_cred

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

        # Establish SSH connection using our refactored module
        client, shell, prompt, debug_log = connect_ssh(hostname, port, profile, debug)

        # Create session object
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
            version_output = send_command(shell, "show version", prompt)
            platform = detect_platform(version_output)
            session.platform = platform
            if debug:
                print(f"[DEBUG] Platform detected: {platform}")
        except Exception as e:
            if debug:
                print(f"[DEBUG] Platform detection failed: {e}")

        # Disable terminal paging
        paging_cmd = get_paging_disable_command(session.platform)
        if paging_cmd:
            try:
                send_command(shell, paging_cmd, prompt, timeout=5)
            except Exception as e:
                if debug:
                    print(f"[DEBUG] Failed to disable paging: {e}")

        self._active_sessions[device_name] = session
        return session

    @contextmanager
    def session(self, device: str, credential: str = None, debug: bool = False) -> Generator[ActiveSession, None, None]:
        """
        Context manager for device sessions with automatic cleanup.

        Args:
            device: Device name (from saved sessions) or hostname
            credential: Optional credential name (auto-resolved if not specified)
            debug: Enable verbose connection debugging

        Yields:
            ActiveSession handle for sending commands

        Raises:
            ConnectionError: If connection fails

        Example:
            # Old way (12 lines):
            session = None
            try:
                session = api.connect(device.name)
                if not session.is_connected():
                    continue
                result = api.send(session, "show version")
            finally:
                if session and session.is_connected():
                    api.disconnect(session)

            # New way (3 lines):
            with api.session(device.name) as s:
                result = api.send(s, "show version")
        """
        sess = None
        try:
            sess = self.connect(device, credential=credential, debug=debug)
            if not sess.is_connected():
                raise ConnectionError(f"Failed to connect to {device}")
            yield sess
        finally:
            if sess and sess.is_connected():
                try:
                    self.disconnect(sess)
                except Exception:
                    pass  # Best effort cleanup

    def send(
        self,
        session: ActiveSession,
        command: str,
        timeout: int = 60,
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

        # Execute command using our refactored module
        raw_output = send_command(session.shell, command, session.prompt, timeout)

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
                                normalized = normalize_fields(
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

    def send_first(
        self,
        session: ActiveSession,
        commands: List[str],
        parse: bool = True,
        timeout: int = 30,
        require_parsed: bool = True,
    ) -> Optional[CommandResult]:
        """
        Try multiple commands until one succeeds (returns parsed data).

        Useful for CDP/LLDP discovery, platform variations, etc.

        Args:
            session: Active session
            commands: List of commands to try in order
            parse: Whether to parse output
            timeout: Command timeout
            require_parsed: If True, only consider success if parsed_data is non-empty

        Returns:
            First successful CommandResult, or None if all failed

        Example:
            # Try CDP first, fall back to LLDP
            result = api.send_first(session, [
                "show cdp neighbors detail",
                "show lldp neighbors detail",
            ])

            # Platform-agnostic config fetch
            result = api.send_first(session, [
                "show running-config",
                "show configuration",
            ], parse=False, require_parsed=False)
        """
        for cmd in commands:
            if cmd is None:
                continue
            try:
                result = self.send(session, cmd, parse=parse, timeout=timeout)

                if require_parsed and parse:
                    # Need non-empty parsed data
                    if result.parsed_data:
                        return result
                else:
                    # Just need non-empty raw output
                    if result.raw_output and result.raw_output.strip():
                        return result

            except Exception:
                continue  # Try next command

        return None

    def send_platform_command(
        self,
        session: ActiveSession,
        command_type: str,
        parse: bool = True,
        timeout: int = 30,
        **kwargs
    ) -> Optional[CommandResult]:
        """
        Send a platform-appropriate command by type.

        Args:
            session: Active session
            command_type: Command type (e.g., 'config', 'version', 'neighbors')
            parse: Whether to parse output
            timeout: Command timeout
            **kwargs: Format arguments (e.g., name='Gi0/1' for interface_detail)

        Returns:
            CommandResult or None if command not available

        Example:
            # Get running config (platform-aware)
            result = api.send_platform_command(session, 'config', parse=False)

            # Get interface details
            result = api.send_platform_command(session, 'interface_detail', name='Gi0/1')
        """
        cmd = get_platform_command(session.platform, command_type, **kwargs)
        if not cmd:
            return None

        return self.send(session, cmd, parse=parse, timeout=timeout)

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

    def disconnect_all(self) -> int:
        """
        Disconnect all active sessions.

        Returns:
            Number of sessions disconnected

        Example:
            # Cleanup at end of script
            count = api.disconnect_all()
            print(f"Disconnected {count} session(s)")
        """
        count = 0
        for session_id in list(self._active_sessions.keys()):
            try:
                session = self._active_sessions[session_id]
                self.disconnect(session)
                count += 1
            except Exception:
                pass
        return count

    def active_sessions(self) -> List[ActiveSession]:
        """
        Get list of currently active sessions.

        Returns:
            List of ActiveSession objects
        """
        # Clean up stale sessions
        active = []
        stale = []

        for session_id, session in self._active_sessions.items():
            if session.is_connected():
                active.append(session)
            else:
                stale.append(session_id)

        # Remove stale entries
        for session_id in stale:
            del self._active_sessions[session_id]

        return active

    # -------------------------------------------------------------------------
    # Debug / diagnostic methods
    # -------------------------------------------------------------------------

    def db_info(self) -> Dict[str, Any]:
        """
        Get detailed information about TextFSM database.

        Returns:
            Dict with database path, existence, and diagnostic info
        """
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
  api.disconnect_all()             Close all connections
  api.active_sessions()            List active connections

Context Manager (recommended):
  with api.session("device") as s:
      result = api.send(s, "show version")
  # Auto-disconnects when done

Platform-Aware Commands:
  api.send_platform_command(s, 'config')           Get running config
  api.send_platform_command(s, 'neighbors')        Get CDP/LLDP neighbors
  api.send_platform_command(s, 'interface_detail', name='Gi0/1')

Try Multiple Commands:
  api.send_first(s, ["show cdp neighbors", "show lldp neighbors"])

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
  # Connect and execute (manual)
  api.unlock("vault-password")
  session = api.connect("spine1")
  result = api.send(session, "show interfaces status")
  api.disconnect(session)
  
  # Connect and execute (context manager - recommended)
  api.unlock("vault-password")
  with api.session("spine1") as s:
      result = api.send(s, "show interfaces status")
      for intf in result.parsed_data:
          print(f"{intf['name']}: {intf['status']}")
  
  # Platform-aware config backup
  with api.session("router1") as s:
      result = api.send_platform_command(s, 'config', parse=False)
      Path("backup.cfg").write_text(result.raw_output)

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