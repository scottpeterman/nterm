"""
Credential resolution - matches credentials to devices.
"""

from __future__ import annotations
import fnmatch
import logging
from typing import Optional

from .store import CredentialStore, StoredCredential
from ..connection.profile import (
    ConnectionProfile, AuthConfig, AuthMethod, JumpHostConfig
)

logger = logging.getLogger(__name__)


class NoCredentialError(Exception):
    """No matching credential found."""
    pass


class CredentialResolver:
    """
    Resolves credentials for devices based on patterns and tags.
    """
    
    def __init__(self, store: CredentialStore = None):
        """
        Initialize resolver.
        
        Args:
            store: Credential store instance
        """
        self.store = store or CredentialStore()
    
    @property
    def db_path(self):
        return self.store.db_path
    
    def is_initialized(self) -> bool:
        return self.store.is_initialized()
    
    def init_vault(self, password: str) -> None:
        self.store.init_vault(password)
    
    def unlock_vault(self, password: str) -> bool:
        return self.store.unlock(password)
    
    def lock_vault(self) -> None:
        self.store.lock()
    
    def add_credential(self, **kwargs) -> int:
        return self.store.add_credential(**kwargs)
    
    def get_credential(self, name: str) -> Optional[StoredCredential]:
        return self.store.get_credential(name)
    
    def list_credentials(self) -> list[StoredCredential]:
        return self.store.list_credentials()
    
    def remove_credential(self, name: str) -> bool:
        return self.store.remove_credential(name)
    
    def set_default(self, name: str) -> bool:
        return self.store.set_default(name)
    
    def resolve_for_device(
        self,
        hostname: str,
        tags: list[str] = None,
        port: int = 22,
    ) -> ConnectionProfile:
        """
        Find best credential match for a device and return a connection profile.
        
        Args:
            hostname: Device hostname or IP
            tags: Optional device tags
            port: SSH port
            
        Returns:
            ConnectionProfile configured for this device
            
        Raises:
            NoCredentialError: No matching credential found
        """
        if not self.store.is_unlocked:
            raise RuntimeError("Vault not unlocked")
        
        creds = self._get_all_credentials()
        candidates = []
        
        for cred in creds:
            score = self._score_credential(cred, hostname, tags)
            if score > 0:
                candidates.append((score, cred))
        
        if not candidates:
            raise NoCredentialError(f"No credential matches {hostname}")
        
        # Highest score wins
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_cred = candidates[0][1]
        
        logger.info(f"Resolved credential '{best_cred.name}' for {hostname}")
        self.store.update_last_used(best_cred.name)
        
        return self._credential_to_profile(best_cred, hostname, port)
    
    def _get_all_credentials(self) -> list[StoredCredential]:
        """Get all credentials with decrypted secrets."""
        # Use the internal connection to get full data
        cursor = self.store._conn.execute("SELECT * FROM credentials")
        return [self.store._row_to_credential(row) for row in cursor]
    
    def _score_credential(
        self,
        cred: StoredCredential,
        hostname: str,
        tags: list[str] = None
    ) -> int:
        """
        Score how well a credential matches a device.
        
        Higher score = better match.
        """
        score = 0
        
        # Check hostname patterns
        for pattern in cred.match_hosts:
            if fnmatch.fnmatch(hostname, pattern):
                # More specific patterns score higher
                specificity = len(pattern) - pattern.count('*') - pattern.count('?')
                score += 10 + specificity
                break
        
        # Check tags
        if tags and cred.match_tags:
            matching_tags = set(tags) & set(cred.match_tags)
            score += len(matching_tags) * 5
        
        # Default credential gets lowest priority
        if cred.is_default and score == 0:
            score = 1
        
        return score
    
    def _credential_to_profile(
        self,
        cred: StoredCredential,
        hostname: str,
        port: int = 22
    ) -> ConnectionProfile:
        """Convert stored credential to connection profile."""
        
        # Build auth methods list
        auth_methods = []
        
        # Key auth takes priority
        if cred.ssh_key:
            auth_methods.append(AuthConfig(
                method=AuthMethod.KEY_STORED,
                username=cred.username,
                key_data=cred.ssh_key,
                key_passphrase=cred.ssh_key_passphrase,
            ))
        
        # Password auth as fallback
        if cred.password:
            auth_methods.append(AuthConfig(
                method=AuthMethod.PASSWORD,
                username=cred.username,
                password=cred.password,
            ))
        
        # Build jump host config if specified
        jump_hosts = []
        if cred.jump_host:
            jump_auth = None
            if cred.jump_auth_method == "agent":
                jump_auth = AuthConfig.agent_auth(cred.jump_username or cred.username)
            elif cred.jump_auth_method == "password" and cred.password:
                jump_auth = AuthConfig.password_auth(
                    cred.jump_username or cred.username,
                    cred.password
                )
            elif cred.jump_auth_method == "key" and cred.ssh_key:
                jump_auth = AuthConfig(
                    method=AuthMethod.KEY_STORED,
                    username=cred.jump_username or cred.username,
                    key_data=cred.ssh_key,
                    key_passphrase=cred.ssh_key_passphrase,
                )
            
            jump_hosts.append(JumpHostConfig(
                hostname=cred.jump_host,
                auth=jump_auth,
                requires_touch=cred.jump_requires_touch,
            ))
        
        return ConnectionProfile(
            name=f"{hostname} ({cred.name})",
            hostname=hostname,
            port=port,
            auth_methods=auth_methods,
            jump_hosts=jump_hosts,
            match_patterns=cred.match_hosts,
            tags=cred.match_tags,
        )
    
    def create_profile_for_credential(
        self,
        credential_name: str,
        hostname: str,
        port: int = 22
    ) -> ConnectionProfile:
        """
        Create connection profile using a specific credential.
        
        Args:
            credential_name: Name of credential in vault
            hostname: Target hostname
            port: SSH port
            
        Returns:
            Configured ConnectionProfile
        """
        cred = self.store.get_credential(credential_name)
        if not cred:
            raise NoCredentialError(f"Credential '{credential_name}' not found")
        
        self.store.update_last_used(credential_name)
        return self._credential_to_profile(cred, hostname, port)
    
    def resolve_or_default(
        self,
        hostname: str,
        tags: list[str] = None,
        port: int = 22,
    ) -> Optional[ConnectionProfile]:
        """
        Try to resolve credential, return None if not found.
        
        Unlike resolve_for_device, this doesn't raise an exception.
        """
        try:
            return self.resolve_for_device(hostname, tags, port)
        except NoCredentialError:
            return None
