"""
Encrypted credential storage using SQLite + Fernet.
"""

from __future__ import annotations
import base64
import hashlib
import logging
import secrets
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


@dataclass
class StoredCredential:
    """Credential stored in vault."""
    id: int
    name: str
    username: str
    
    # Auth options (encrypted at rest)
    password: Optional[str] = None
    ssh_key: Optional[str] = None
    ssh_key_passphrase: Optional[str] = None
    
    # Jump host config
    jump_host: Optional[str] = None
    jump_username: Optional[str] = None
    jump_auth_method: str = "agent"  # agent, password, key
    jump_requires_touch: bool = False
    
    # Matching rules
    match_hosts: list[str] = field(default_factory=list)
    match_tags: list[str] = field(default_factory=list)
    
    # Metadata
    is_default: bool = False
    created_at: Optional[datetime] = None
    last_used: Optional[datetime] = None
    
    @property
    def has_password(self) -> bool:
        return self.password is not None and len(self.password) > 0
    
    @property
    def has_ssh_key(self) -> bool:
        return self.ssh_key is not None and len(self.ssh_key) > 0


class CredentialStore:
    """
    Encrypted credential storage.
    
    Uses SQLite for storage and Fernet for encryption.
    Master password is required to unlock the vault.
    """
    
    SCHEMA_VERSION = 1
    
    def __init__(self, db_path: Path = None):
        """
        Initialize credential store.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path or Path.home() / ".nterm" / "vault.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._conn: Optional[sqlite3.Connection] = None
        self._fernet: Optional[Fernet] = None
        self._unlocked = False
    
    def is_initialized(self) -> bool:
        """Check if vault has been initialized."""
        if not self.db_path.exists():
            return False
        
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='vault_meta'"
            )
            return cursor.fetchone() is not None
        finally:
            conn.close()
    
    def init_vault(self, password: str) -> None:
        """
        Initialize vault with master password.
        
        Args:
            password: Master password for encryption
        """
        if self.is_initialized():
            raise RuntimeError("Vault already initialized")
        
        # Generate salt for key derivation
        salt = secrets.token_bytes(16)
        
        # Derive key from password
        key = self._derive_key(password, salt)
        
        # Create verification token
        verify_token = secrets.token_bytes(32)
        fernet = Fernet(key)
        encrypted_verify = fernet.encrypt(verify_token)
        
        # Create database
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.executescript('''
                CREATE TABLE vault_meta (
                    key TEXT PRIMARY KEY,
                    value BLOB
                );
                
                CREATE TABLE credentials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    username TEXT NOT NULL,
                    password_enc BLOB,
                    ssh_key_enc BLOB,
                    ssh_key_passphrase_enc BLOB,
                    jump_host TEXT,
                    jump_username TEXT,
                    jump_auth_method TEXT DEFAULT 'agent',
                    jump_requires_touch INTEGER DEFAULT 0,
                    match_hosts TEXT,
                    match_tags TEXT,
                    is_default INTEGER DEFAULT 0,
                    created_at TEXT,
                    last_used TEXT
                );
                
                CREATE INDEX idx_credentials_name ON credentials(name);
                CREATE INDEX idx_credentials_default ON credentials(is_default);
            ''')
            
            conn.execute(
                "INSERT INTO vault_meta (key, value) VALUES (?, ?)",
                ('salt', salt)
            )
            conn.execute(
                "INSERT INTO vault_meta (key, value) VALUES (?, ?)",
                ('verify', encrypted_verify)
            )
            conn.execute(
                "INSERT INTO vault_meta (key, value) VALUES (?, ?)",
                ('verify_plain', verify_token)
            )
            conn.execute(
                "INSERT INTO vault_meta (key, value) VALUES (?, ?)",
                ('version', str(self.SCHEMA_VERSION).encode())
            )
            conn.commit()
        finally:
            conn.close()
        
        logger.info(f"Vault initialized at {self.db_path}")
    
    def unlock(self, password: str) -> bool:
        """
        Unlock vault with master password.
        
        Args:
            password: Master password
            
        Returns:
            True if unlock successful
        """
        if not self.is_initialized():
            raise RuntimeError("Vault not initialized")
        
        conn = sqlite3.connect(str(self.db_path))
        try:
            # Get salt
            cursor = conn.execute(
                "SELECT value FROM vault_meta WHERE key = ?", ('salt',)
            )
            row = cursor.fetchone()
            if not row:
                return False
            salt = row[0]
            
            # Derive key
            key = self._derive_key(password, salt)
            fernet = Fernet(key)
            
            # Verify password
            cursor = conn.execute(
                "SELECT value FROM vault_meta WHERE key = ?", ('verify',)
            )
            row = cursor.fetchone()
            if not row:
                return False
            encrypted_verify = row[0]
            
            cursor = conn.execute(
                "SELECT value FROM vault_meta WHERE key = ?", ('verify_plain',)
            )
            row = cursor.fetchone()
            if not row:
                return False
            verify_plain = row[0]
            
            try:
                decrypted = fernet.decrypt(encrypted_verify)
                if decrypted != verify_plain:
                    return False
            except InvalidToken:
                return False
            
            # Success - store connection and fernet
            self._conn = conn
            self._fernet = fernet
            self._unlocked = True
            logger.info("Vault unlocked")
            return True
            
        except Exception as e:
            logger.exception(f"Unlock failed: {e}")
            conn.close()
            return False
    
    def lock(self) -> None:
        """Lock vault."""
        if self._conn:
            self._conn.close()
            self._conn = None
        self._fernet = None
        self._unlocked = False
        logger.info("Vault locked")
    
    @property
    def is_unlocked(self) -> bool:
        """Check if vault is unlocked."""
        return self._unlocked and self._fernet is not None
    
    def _derive_key(self, password: str, salt: bytes) -> bytes:
        """Derive encryption key from password."""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key
    
    def _encrypt(self, data: str) -> bytes:
        """Encrypt string data."""
        if not self._fernet:
            raise RuntimeError("Vault not unlocked")
        return self._fernet.encrypt(data.encode())
    
    def _decrypt(self, data: bytes) -> str:
        """Decrypt to string."""
        if not self._fernet:
            raise RuntimeError("Vault not unlocked")
        return self._fernet.decrypt(data).decode()
    
    def add_credential(
        self,
        name: str,
        username: str,
        password: str = None,
        ssh_key: str = None,
        ssh_key_passphrase: str = None,
        jump_host: str = None,
        jump_username: str = None,
        jump_auth_method: str = "agent",
        jump_requires_touch: bool = False,
        match_hosts: list[str] = None,
        match_tags: list[str] = None,
        is_default: bool = False,
    ) -> int:
        """
        Add credential to vault.
        
        Returns:
            Credential ID
        """
        if not self.is_unlocked:
            raise RuntimeError("Vault not unlocked")
        
        # Encrypt sensitive fields
        password_enc = self._encrypt(password) if password else None
        ssh_key_enc = self._encrypt(ssh_key.strip()) if ssh_key else None
        ssh_key_pass_enc = self._encrypt(ssh_key_passphrase) if ssh_key_passphrase else None
        
        # Serialize lists
        match_hosts_str = ",".join(match_hosts) if match_hosts else None
        match_tags_str = ",".join(match_tags) if match_tags else None
        
        # If setting as default, clear other defaults
        if is_default:
            self._conn.execute("UPDATE credentials SET is_default = 0")
        
        cursor = self._conn.execute('''
            INSERT INTO credentials (
                name, username, password_enc, ssh_key_enc, ssh_key_passphrase_enc,
                jump_host, jump_username, jump_auth_method, jump_requires_touch,
                match_hosts, match_tags, is_default, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            name, username, password_enc, ssh_key_enc, ssh_key_pass_enc,
            jump_host, jump_username, jump_auth_method, int(jump_requires_touch),
            match_hosts_str, match_tags_str, int(is_default),
            datetime.now().isoformat()
        ))
        
        self._conn.commit()
        return cursor.lastrowid
    
    def get_credential(self, name: str) -> Optional[StoredCredential]:
        """
        Get credential by name.
        
        Args:
            name: Credential name
            
        Returns:
            StoredCredential if found
        """
        if not self.is_unlocked:
            raise RuntimeError("Vault not unlocked")
        
        cursor = self._conn.execute(
            "SELECT * FROM credentials WHERE name = ?", (name,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        
        return self._row_to_credential(row)
    
    def get_credential_by_id(self, cred_id: int) -> Optional[StoredCredential]:
        """Get credential by ID."""
        if not self.is_unlocked:
            raise RuntimeError("Vault not unlocked")
        
        cursor = self._conn.execute(
            "SELECT * FROM credentials WHERE id = ?", (cred_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        
        return self._row_to_credential(row)
    
    def list_credentials(self) -> list[StoredCredential]:
        """
        List all credentials (without decrypting secrets).
        
        Returns:
            List of credentials with metadata only
        """
        # This works even when locked - just returns metadata
        conn = self._conn or sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.execute('''
                SELECT id, name, username, 
                       password_enc IS NOT NULL as has_password,
                       ssh_key_enc IS NOT NULL as has_ssh_key,
                       is_default, created_at, last_used
                FROM credentials
                ORDER BY name
            ''')
            
            results = []
            for row in cursor:
                cred = StoredCredential(
                    id=row[0],
                    name=row[1],
                    username=row[2],
                    is_default=bool(row[5]),
                    created_at=datetime.fromisoformat(row[6]) if row[6] else None,
                    last_used=datetime.fromisoformat(row[7]) if row[7] else None,
                )
                # Set flags for display
                cred.password = "***" if row[3] else None
                cred.ssh_key = "***" if row[4] else None
                results.append(cred)
            
            return results
        finally:
            if not self._conn:
                conn.close()
    
    def _row_to_credential(self, row) -> StoredCredential:
        """Convert database row to StoredCredential."""
        # Decrypt sensitive fields
        password = self._decrypt(row[3]) if row[3] else None
        ssh_key = self._decrypt(row[4]) if row[4] else None
        ssh_key_passphrase = self._decrypt(row[5]) if row[5] else None
        
        # Parse lists
        match_hosts = row[10].split(",") if row[10] else []
        match_tags = row[11].split(",") if row[11] else []
        
        return StoredCredential(
            id=row[0],
            name=row[1],
            username=row[2],
            password=password,
            ssh_key=ssh_key,
            ssh_key_passphrase=ssh_key_passphrase,
            jump_host=row[6],
            jump_username=row[7],
            jump_auth_method=row[8] or "agent",
            jump_requires_touch=bool(row[9]),
            match_hosts=match_hosts,
            match_tags=match_tags,
            is_default=bool(row[12]),
            created_at=datetime.fromisoformat(row[13]) if row[13] else None,
            last_used=datetime.fromisoformat(row[14]) if row[14] else None,
        )
    
    def remove_credential(self, name: str) -> bool:
        """
        Remove credential by name.
        
        Returns:
            True if removed
        """
        conn = self._conn or sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.execute(
                "DELETE FROM credentials WHERE name = ?", (name,)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            if not self._conn:
                conn.close()
    
    def set_default(self, name: str) -> bool:
        """
        Set credential as default.
        
        Returns:
            True if successful
        """
        conn = self._conn or sqlite3.connect(str(self.db_path))
        try:
            conn.execute("UPDATE credentials SET is_default = 0")
            cursor = conn.execute(
                "UPDATE credentials SET is_default = 1 WHERE name = ?", (name,)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            if not self._conn:
                conn.close()
    
    def get_default(self) -> Optional[StoredCredential]:
        """Get default credential."""
        if not self.is_unlocked:
            raise RuntimeError("Vault not unlocked")
        
        cursor = self._conn.execute(
            "SELECT * FROM credentials WHERE is_default = 1"
        )
        row = cursor.fetchone()
        if not row:
            return None
        
        return self._row_to_credential(row)
    
    def update_last_used(self, name: str) -> None:
        """Update last used timestamp."""
        conn = self._conn or sqlite3.connect(str(self.db_path))
        try:
            conn.execute(
                "UPDATE credentials SET last_used = ? WHERE name = ?",
                (datetime.now().isoformat(), name)
            )
            conn.commit()
        finally:
            if not self._conn:
                conn.close()
    
    def update_credential(
        self,
        name: str,
        **kwargs
    ) -> bool:
        """
        Update an existing credential.
        
        Args:
            name: Credential name to update
            **kwargs: Fields to update
            
        Returns:
            True if updated
        """
        if not self.is_unlocked:
            raise RuntimeError("Vault not unlocked")
        
        # Get existing credential
        existing = self.get_credential(name)
        if not existing:
            return False
        
        # Build update data - merge existing with new
        updates = {}
        
        if 'username' in kwargs:
            updates['username'] = kwargs['username']
        
        if 'password' in kwargs:
            updates['password_enc'] = self._encrypt(kwargs['password']) if kwargs['password'] else None
        
        if 'ssh_key' in kwargs:
            updates['ssh_key_enc'] = self._encrypt(kwargs['ssh_key'].strip()) if kwargs['ssh_key'] else None

        if 'ssh_key_passphrase' in kwargs:
            updates['ssh_key_passphrase_enc'] = self._encrypt(kwargs['ssh_key_passphrase']) if kwargs['ssh_key_passphrase'] else None
        
        if 'jump_host' in kwargs:
            updates['jump_host'] = kwargs['jump_host']
        
        if 'jump_username' in kwargs:
            updates['jump_username'] = kwargs['jump_username']
        
        if 'jump_auth_method' in kwargs:
            updates['jump_auth_method'] = kwargs['jump_auth_method']
        
        if 'jump_requires_touch' in kwargs:
            updates['jump_requires_touch'] = int(kwargs['jump_requires_touch'])
        
        if 'match_hosts' in kwargs:
            updates['match_hosts'] = ",".join(kwargs['match_hosts']) if kwargs['match_hosts'] else None
        
        if 'match_tags' in kwargs:
            updates['match_tags'] = ",".join(kwargs['match_tags']) if kwargs['match_tags'] else None
        
        if 'is_default' in kwargs:
            if kwargs['is_default']:
                self._conn.execute("UPDATE credentials SET is_default = 0")
            updates['is_default'] = int(kwargs['is_default'])
        
        if not updates:
            return True  # Nothing to update
        
        # Build SQL
        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [name]
        
        cursor = self._conn.execute(
            f"UPDATE credentials SET {set_clause} WHERE name = ?",
            values
        )
        self._conn.commit()
        
        return cursor.rowcount > 0
    
    def change_master_password(self, old_password: str, new_password: str) -> bool:
        """
        Change the master password.
        
        Re-encrypts all credentials with new password.
        
        Args:
            old_password: Current master password
            new_password: New master password
            
        Returns:
            True if successful
        """
        # Verify old password works
        if not self.unlock(old_password):
            return False
        
        # Get all credentials with decrypted data
        credentials = []
        cursor = self._conn.execute("SELECT * FROM credentials")
        for row in cursor:
            credentials.append(self._row_to_credential(row))
        
        # Generate new salt and key
        new_salt = secrets.token_bytes(16)
        new_key = self._derive_key(new_password, new_salt)
        new_fernet = Fernet(new_key)
        
        # Create new verification token
        verify_token = secrets.token_bytes(32)
        encrypted_verify = new_fernet.encrypt(verify_token)
        
        # Update vault metadata
        self._conn.execute(
            "UPDATE vault_meta SET value = ? WHERE key = ?",
            (new_salt, 'salt')
        )
        self._conn.execute(
            "UPDATE vault_meta SET value = ? WHERE key = ?",
            (encrypted_verify, 'verify')
        )
        self._conn.execute(
            "UPDATE vault_meta SET value = ? WHERE key = ?",
            (verify_token, 'verify_plain')
        )
        
        # Re-encrypt all credentials
        for cred in credentials:
            updates = {}
            
            if cred.password:
                updates['password_enc'] = new_fernet.encrypt(cred.password.encode())
            
            if cred.ssh_key:
                updates['ssh_key_enc'] = new_fernet.encrypt(cred.ssh_key.encode())
            
            if cred.ssh_key_passphrase:
                updates['ssh_key_passphrase_enc'] = new_fernet.encrypt(cred.ssh_key_passphrase.encode())
            
            if updates:
                set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
                values = list(updates.values()) + [cred.name]
                self._conn.execute(
                    f"UPDATE credentials SET {set_clause} WHERE name = ?",
                    values
                )
        
        self._conn.commit()
        
        # Update internal state
        self._fernet = new_fernet
        
        logger.info("Master password changed successfully")
        return True
