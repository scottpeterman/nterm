"""
nterm/scripting/models.py

Data models for the scripting API.
"""

from __future__ import annotations
import paramiko
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict, field
from datetime import datetime

from ..manager.models import SavedSession


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
