"""
nterm.scripting - Scripting API for nterm

Provides programmatic access to nterm's device sessions and credential vault.
Usable from IPython, CLI, scripts, or as foundation for MCP tools.

Quick Start (IPython):
    from nterm.scripting import api

    api.devices()                  # List all saved devices
    api.search("leaf")             # Search devices
    api.device("eng-leaf-1")       # Get specific device

    api.unlock("vault-password")   # Unlock credential vault
    api.credentials()              # List credentials

    api.help()                     # Show all commands

Quick Start (CLI):
    nterm-cli devices
    nterm-cli search leaf
    nterm-cli credentials --unlock
"""

from .api import (
    NTermAPI,
    DeviceInfo,
    CredentialInfo,
    get_api,
    reset_api,
)

# Convenience: pre-instantiated API
api = get_api()

__all__ = [
    "NTermAPI",
    "DeviceInfo",
    "CredentialInfo",
    "get_api",
    "reset_api",
    "api",
]