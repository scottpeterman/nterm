"""
Credential vault - encrypted credential storage with UI.
"""

from .store import CredentialStore, StoredCredential
from .resolver import CredentialResolver, NoCredentialError
from .keychain import KeychainIntegration, KEYRING_AVAILABLE
from .manager_ui import (
    CredentialManagerWidget,
    CredentialDialog,
    UnlockDialog,
    ManagerTheme,
    run_standalone,
)

__all__ = [
    # Store
    "CredentialStore",
    "StoredCredential",
    # Resolver
    "CredentialResolver",
    "NoCredentialError",
    # Keychain
    "KeychainIntegration",
    "KEYRING_AVAILABLE",
    # UI
    "CredentialManagerWidget",
    "CredentialDialog",
    "UnlockDialog",
    "ManagerTheme",
    "run_standalone",
]
