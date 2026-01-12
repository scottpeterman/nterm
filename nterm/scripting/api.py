"""
nterm/scripting/api.py

Scripting API for nterm - usable from IPython, CLI, or MCP tools.
"""

from __future__ import annotations
import fnmatch
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict

from ..manager.models import SessionStore, SavedSession, SessionFolder
from ..vault.resolver import CredentialResolver
from ..vault.store import StoredCredential


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
    ):
        self._sessions = session_store or SessionStore()
        self._resolver = credential_resolver or CredentialResolver()
        self._folder_cache: Dict[int, str] = {}
        self._active_sessions: Dict[str, Any] = {}  # Future: track open sessions

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
    # Connection operations (future expansion)
    # -------------------------------------------------------------------------

    def connect(self, device: str, credential: str = None):
        """
        Connect to a device.

        Args:
            device: Device name (from saved sessions) or hostname
            credential: Optional credential name (auto-resolved if not specified)

        Returns:
            Session handle for sending commands
        """
        # TODO: Implement actual connection logic
        raise NotImplementedError("Connection support coming soon")

    def send(self, session, command: str, timeout: int = 30) -> str:
        """
        Send command to a connected session.

        Args:
            session: Session handle from connect()
            command: Command to execute
            timeout: Timeout in seconds

        Returns:
            Command output
        """
        raise NotImplementedError("Connection support coming soon")

    def disconnect(self, session) -> None:
        """Disconnect a session."""
        raise NotImplementedError("Connection support coming soon")

    # -------------------------------------------------------------------------
    # Convenience / REPL helpers
    # -------------------------------------------------------------------------

    def __repr__(self) -> str:
        device_count = len(self._sessions.list_all_sessions())
        vault_status = "unlocked" if self.vault_unlocked else "locked"
        return f"<NTermAPI: {device_count} devices, vault {vault_status}>"

    def status(self) -> Dict[str, Any]:
        """
        Get API status summary.

        Returns:
            Dict with device count, folder count, credential count, vault status
        """
        sessions = self._sessions.list_all_sessions()
        folders = self._sessions.get_tree()["folders"]

        cred_count = 0
        if self.vault_unlocked:
            cred_count = len(self._resolver.list_credentials())

        return {
            "devices": len(sessions),
            "folders": len(folders),
            "credentials": cred_count,
            "vault_initialized": self.vault_initialized,
            "vault_unlocked": self.vault_unlocked,
            "active_sessions": len(self._active_sessions),
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

Status:
  api.status()                     Get summary
  api.vault_unlocked               Check vault status
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