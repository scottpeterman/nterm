"""
Connection profiles - everything needed to establish and re-establish a connection.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import json
import yaml


class AuthMethod(Enum):
    """Supported authentication methods."""
    PASSWORD = "password"
    KEY_FILE = "key_file"
    KEY_STORED = "key_stored"      # Key material in vault
    AGENT = "agent"                 # ssh-agent (YubiKey/FIDO2)
    KEYBOARD_INTERACTIVE = "keyboard_interactive"
    CERTIFICATE = "certificate"
    
    def requires_interaction(self) -> bool:
        """Does this method potentially need user interaction?"""
        return self in (
            AuthMethod.AGENT,  # YubiKey touch
            AuthMethod.KEYBOARD_INTERACTIVE,
        )


@dataclass
class AuthConfig:
    """Authentication configuration for a single method."""
    method: AuthMethod
    username: str
    
    # Password auth
    password: Optional[str] = None
    credential_ref: Optional[str] = None  # Vault reference instead of plaintext
    
    # Key auth
    key_path: Optional[str] = None        # Path to key file
    key_data: Optional[str] = None        # Raw key (from vault)
    key_passphrase: Optional[str] = None
    
    # Certificate auth
    cert_path: Optional[str] = None
    
    # Agent settings
    agent_socket: Optional[str] = None    # Override SSH_AUTH_SOCK
    
    # Behavior
    allow_agent_fallback: bool = False
    
    def to_dict(self) -> dict:
        """Serialize, excluding secrets."""
        d = {
            'method': self.method.value,
            'username': self.username,
            'key_path': self.key_path,
            'cert_path': self.cert_path,
            'credential_ref': self.credential_ref,
            'allow_agent_fallback': self.allow_agent_fallback,
        }
        # Never serialize: password, key_data, key_passphrase
        return {k: v for k, v in d.items() if v is not None}
    
    @classmethod
    def from_dict(cls, data: dict) -> AuthConfig:
        """Deserialize from dict."""
        data = data.copy()
        data['method'] = AuthMethod(data['method'])
        return cls(**data)
    
    @classmethod
    def password_auth(
        cls, 
        username: str, 
        password: str = None, 
        credential_ref: str = None
    ) -> AuthConfig:
        """Factory for password auth."""
        return cls(
            method=AuthMethod.PASSWORD,
            username=username,
            password=password,
            credential_ref=credential_ref,
        )
    
    @classmethod
    def agent_auth(cls, username: str, allow_fallback: bool = False) -> AuthConfig:
        """Factory for ssh-agent auth (YubiKey, etc)."""
        return cls(
            method=AuthMethod.AGENT,
            username=username,
            allow_agent_fallback=allow_fallback,
        )
    
    @classmethod
    def key_file_auth(
        cls, 
        username: str, 
        key_path: str, 
        passphrase: str = None
    ) -> AuthConfig:
        """Factory for key file auth."""
        return cls(
            method=AuthMethod.KEY_FILE,
            username=username,
            key_path=key_path,
            key_passphrase=passphrase,
        )
    
    @classmethod
    def stored_key_auth(
        cls,
        username: str,
        credential_ref: str,
        allow_fallback: bool = False
    ) -> AuthConfig:
        """Factory for vault-stored key auth."""
        return cls(
            method=AuthMethod.KEY_STORED,
            username=username,
            credential_ref=credential_ref,
            allow_agent_fallback=allow_fallback,
        )


@dataclass
class JumpHostConfig:
    """Jump host / bastion configuration."""
    hostname: str
    port: int = 22
    auth: AuthConfig = None
    
    # Interaction hints for UI
    requires_touch: bool = False
    touch_prompt: str = "Touch your security key..."
    banner_timeout: float = 30.0
    
    def to_dict(self) -> dict:
        """Serialize to dict."""
        return {
            'hostname': self.hostname,
            'port': self.port,
            'auth': self.auth.to_dict() if self.auth else None,
            'requires_touch': self.requires_touch,
            'touch_prompt': self.touch_prompt,
            'banner_timeout': self.banner_timeout,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> JumpHostConfig:
        """Deserialize from dict."""
        data = data.copy()
        if data.get('auth'):
            data['auth'] = AuthConfig.from_dict(data['auth'])
        return cls(**data)


@dataclass
class ConnectionProfile:
    """
    Complete connection specification.
    
    This is the "recipe" for a connection - everything needed to 
    establish it, and re-establish it if dropped.
    """
    name: str
    hostname: str
    port: int = 22
    
    # Auth methods - tried in order until one succeeds
    auth_methods: list[AuthConfig] = field(default_factory=list)
    
    # Jump host chain (in order)
    jump_hosts: list[JumpHostConfig] = field(default_factory=list)
    
    # Terminal settings
    term_type: str = "xterm-256color"
    term_cols: int = 120
    term_rows: int = 40
    
    # Connection behavior
    keepalive_interval: int = 30
    keepalive_count_max: int = 3
    connect_timeout: float = 30.0
    
    # Reconnection policy
    auto_reconnect: bool = True
    reconnect_delay: float = 2.0
    reconnect_max_attempts: int = 5
    reconnect_backoff: float = 1.5  # Exponential backoff multiplier
    
    # Matching rules (for credential resolver)
    match_patterns: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    
    # Metadata
    description: str = ""
    group: str = ""  # For UI grouping
    
    def to_dict(self) -> dict:
        """Serialize to dict (for saving)."""
        return {
            'name': self.name,
            'hostname': self.hostname,
            'port': self.port,
            'auth_methods': [a.to_dict() for a in self.auth_methods],
            'jump_hosts': [j.to_dict() for j in self.jump_hosts],
            'term_type': self.term_type,
            'term_cols': self.term_cols,
            'term_rows': self.term_rows,
            'keepalive_interval': self.keepalive_interval,
            'keepalive_count_max': self.keepalive_count_max,
            'connect_timeout': self.connect_timeout,
            'auto_reconnect': self.auto_reconnect,
            'reconnect_delay': self.reconnect_delay,
            'reconnect_max_attempts': self.reconnect_max_attempts,
            'reconnect_backoff': self.reconnect_backoff,
            'match_patterns': self.match_patterns,
            'tags': self.tags,
            'description': self.description,
            'group': self.group,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> ConnectionProfile:
        """Deserialize from dict."""
        data = data.copy()
        data['auth_methods'] = [
            AuthConfig.from_dict(a) for a in data.get('auth_methods', [])
        ]
        data['jump_hosts'] = [
            JumpHostConfig.from_dict(j) for j in data.get('jump_hosts', [])
        ]
        return cls(**data)
    
    def to_yaml(self) -> str:
        """Serialize to YAML string."""
        return yaml.dump(self.to_dict(), default_flow_style=False, sort_keys=False)
    
    @classmethod
    def from_yaml(cls, yaml_str: str) -> ConnectionProfile:
        """Deserialize from YAML string."""
        return cls.from_dict(yaml.safe_load(yaml_str))
    
    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)
    
    @classmethod
    def from_json(cls, json_str: str) -> ConnectionProfile:
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))
    
    def save(self, path: str) -> None:
        """Save to file (YAML or JSON based on extension)."""
        from pathlib import Path
        p = Path(path)
        content = self.to_yaml() if p.suffix in ('.yaml', '.yml') else self.to_json()
        p.write_text(content)
    
    @classmethod
    def load(cls, path: str) -> ConnectionProfile:
        """Load from file (YAML or JSON based on extension)."""
        from pathlib import Path
        p = Path(path)
        content = p.read_text()
        if p.suffix in ('.yaml', '.yml'):
            return cls.from_yaml(content)
        return cls.from_json(content)
    
    @property
    def requires_interaction(self) -> bool:
        """Does this connection require user interaction to establish?"""
        for jump in self.jump_hosts:
            if jump.requires_touch:
                return True
            if jump.auth and jump.auth.method.requires_interaction():
                return True
        return any(a.method.requires_interaction() for a in self.auth_methods)
    
    @property
    def display_name(self) -> str:
        """User-friendly display string."""
        if self.jump_hosts:
            chain = " → ".join(j.hostname for j in self.jump_hosts)
            return f"{chain} → {self.hostname}"
        return self.hostname
    
    def clone(self, **overrides) -> ConnectionProfile:
        """Create a copy with optional overrides."""
        data = self.to_dict()
        data.update(overrides)
        return ConnectionProfile.from_dict(data)
