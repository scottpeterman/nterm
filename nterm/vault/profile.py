"""
Connection profile definitions for SSH sessions.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


class AuthMethod(Enum):
    """SSH authentication method."""
    PASSWORD = auto()
    KEY_FILE = auto()
    KEY_STORED = auto()  # Key data stored in vault
    AGENT = auto()


@dataclass
class AuthConfig:
    """Authentication configuration."""
    method: AuthMethod
    username: str
    
    # For PASSWORD method
    password: Optional[str] = None
    
    # For KEY_FILE method
    key_path: Optional[str] = None
    
    # For KEY_STORED method
    key_data: Optional[str] = None
    
    # For KEY_FILE and KEY_STORED
    key_passphrase: Optional[str] = None
    
    @classmethod
    def password_auth(cls, username: str, password: str) -> AuthConfig:
        """Create password authentication config."""
        return cls(
            method=AuthMethod.PASSWORD,
            username=username,
            password=password,
        )
    
    @classmethod
    def key_file_auth(
        cls,
        username: str,
        key_path: str,
        passphrase: str = None
    ) -> AuthConfig:
        """Create key file authentication config."""
        return cls(
            method=AuthMethod.KEY_FILE,
            username=username,
            key_path=key_path,
            key_passphrase=passphrase,
        )
    
    @classmethod
    def key_data_auth(
        cls,
        username: str,
        key_data: str,
        passphrase: str = None
    ) -> AuthConfig:
        """Create stored key authentication config."""
        return cls(
            method=AuthMethod.KEY_STORED,
            username=username,
            key_data=key_data,
            key_passphrase=passphrase,
        )
    
    @classmethod
    def agent_auth(cls, username: str) -> AuthConfig:
        """Create SSH agent authentication config."""
        return cls(
            method=AuthMethod.AGENT,
            username=username,
        )


@dataclass
class JumpHostConfig:
    """Jump host (bastion) configuration."""
    hostname: str
    port: int = 22
    auth: Optional[AuthConfig] = None
    
    # YubiKey / FIDO support
    requires_touch: bool = False
    touch_prompt: Optional[str] = None
    touch_timeout: int = 30  # seconds
    
    def __post_init__(self):
        if self.requires_touch and not self.touch_prompt:
            self.touch_prompt = f"Touch your security key for {self.hostname}..."


@dataclass
class ConnectionProfile:
    """
    Complete SSH connection profile.
    
    Defines everything needed to establish an SSH connection,
    including authentication, jump hosts, and reconnection behavior.
    """
    name: str
    hostname: str
    port: int = 22
    
    # Authentication methods (tried in order)
    auth_methods: List[AuthConfig] = field(default_factory=list)
    
    # Jump hosts (chained in order)
    jump_hosts: List[JumpHostConfig] = field(default_factory=list)
    
    # Connection behavior
    auto_reconnect: bool = False
    reconnect_delay: float = 3.0
    max_reconnect_attempts: int = 5
    connect_timeout: float = 30.0
    keepalive_interval: int = 60
    
    # Terminal settings
    terminal_type: str = "xterm-256color"
    initial_env: dict = field(default_factory=dict)
    
    # Matching metadata (for credential resolution)
    match_patterns: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    
    @property
    def primary_username(self) -> Optional[str]:
        """Get username from first auth method."""
        if self.auth_methods:
            return self.auth_methods[0].username
        return None
    
    @property
    def has_jump_host(self) -> bool:
        """Check if connection uses jump hosts."""
        return len(self.jump_hosts) > 0
    
    @property
    def requires_touch(self) -> bool:
        """Check if any jump host requires touch authentication."""
        return any(jh.requires_touch for jh in self.jump_hosts)
    
    def get_display_name(self) -> str:
        """Get human-readable connection name."""
        user = self.primary_username or "unknown"
        if self.has_jump_host:
            jump = self.jump_hosts[0].hostname
            return f"{user}@{self.hostname} (via {jump})"
        return f"{user}@{self.hostname}"
    
    def to_dict(self) -> dict:
        """Serialize profile to dictionary."""
        return {
            "name": self.name,
            "hostname": self.hostname,
            "port": self.port,
            "auto_reconnect": self.auto_reconnect,
            "reconnect_delay": self.reconnect_delay,
            "max_reconnect_attempts": self.max_reconnect_attempts,
            "connect_timeout": self.connect_timeout,
            "keepalive_interval": self.keepalive_interval,
            "terminal_type": self.terminal_type,
            "match_patterns": self.match_patterns,
            "tags": self.tags,
            # Note: auth_methods and jump_hosts contain secrets
            # and should not be serialized to plain dict
        }
    
    @classmethod
    def simple(
        cls,
        hostname: str,
        username: str,
        password: str = None,
        key_path: str = None,
        port: int = 22,
    ) -> ConnectionProfile:
        """
        Create a simple connection profile.
        
        Args:
            hostname: Target hostname
            username: SSH username
            password: Optional password
            key_path: Optional path to private key
            port: SSH port
            
        Returns:
            Configured ConnectionProfile
        """
        auth_methods = []
        
        if key_path:
            auth_methods.append(AuthConfig.key_file_auth(username, key_path))
        
        # Try agent
        auth_methods.append(AuthConfig.agent_auth(username))
        
        if password:
            auth_methods.append(AuthConfig.password_auth(username, password))
        
        return cls(
            name=f"{username}@{hostname}",
            hostname=hostname,
            port=port,
            auth_methods=auth_methods,
        )
