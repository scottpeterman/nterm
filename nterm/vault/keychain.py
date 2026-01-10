"""
Cross-platform keychain integration for master password storage.

Supports:
- macOS: Keychain
- Windows: Credential Locker
- Linux: Secret Service (GNOME Keyring / KWallet)
"""

from __future__ import annotations
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Try to import keyring - it's optional
try:
    import keyring
    from keyring.errors import PasswordDeleteError, KeyringError
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False
    logger.debug("keyring not available - install with: pip install keyring")


class KeychainIntegration:
    """
    Optional system keychain integration for master password caching.
    
    This doesn't replace the vault's encryption - it just caches the
    master password so users don't have to type it every session.
    """
    
    SERVICE_NAME = "nterm-vault"
    ACCOUNT_NAME = "master-password"
    
    @classmethod
    def is_available(cls) -> bool:
        """Check if system keychain is available and functional."""
        if not KEYRING_AVAILABLE:
            return False
        
        try:
            # Probe the keychain backend
            backend = keyring.get_keyring()
            # Check it's not the fail backend
            backend_name = type(backend).__name__
            if "Fail" in backend_name or "Null" in backend_name:
                logger.debug(f"Keyring backend not usable: {backend_name}")
                return False
            logger.debug(f"Keyring backend: {backend_name}")
            return True
        except Exception as e:
            logger.debug(f"Keyring probe failed: {e}")
            return False
    
    @classmethod
    def get_backend_name(cls) -> Optional[str]:
        """Get the name of the active keyring backend."""
        if not KEYRING_AVAILABLE:
            return None
        try:
            return type(keyring.get_keyring()).__name__
        except Exception:
            return None
    
    @classmethod
    def store_master_password(cls, password: str) -> bool:
        """
        Store master password in system keychain.
        
        Args:
            password: The master vault password
            
        Returns:
            True if stored successfully
        """
        if not cls.is_available():
            logger.warning("Keychain not available")
            return False
        
        try:
            keyring.set_password(cls.SERVICE_NAME, cls.ACCOUNT_NAME, password)
            logger.info("Master password stored in system keychain")
            return True
        except Exception as e:
            logger.error(f"Failed to store password in keychain: {e}")
            return False
    
    @classmethod
    def get_master_password(cls) -> Optional[str]:
        """
        Retrieve master password from system keychain.
        
        Returns:
            Password if found, None otherwise
        """
        if not KEYRING_AVAILABLE:
            return None
        
        try:
            password = keyring.get_password(cls.SERVICE_NAME, cls.ACCOUNT_NAME)
            if password:
                logger.debug("Retrieved master password from keychain")
            return password
        except Exception as e:
            logger.debug(f"Failed to get password from keychain: {e}")
            return None
    
    @classmethod
    def clear_master_password(cls) -> bool:
        """
        Remove master password from system keychain.
        
        Returns:
            True if removed (or wasn't present)
        """
        if not KEYRING_AVAILABLE:
            return False
        
        try:
            keyring.delete_password(cls.SERVICE_NAME, cls.ACCOUNT_NAME)
            logger.info("Master password removed from system keychain")
            return True
        except PasswordDeleteError:
            # Password wasn't stored - that's fine
            return True
        except Exception as e:
            logger.error(f"Failed to remove password from keychain: {e}")
            return False
    
    @classmethod
    def has_stored_password(cls) -> bool:
        """Check if a password is stored without retrieving it."""
        return cls.get_master_password() is not None
