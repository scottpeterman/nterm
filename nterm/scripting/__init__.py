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
"""

from .api import (
    NTermAPI,
    DeviceInfo,
    CredentialInfo,
    get_api,
    reset_api,
)
from nterm.scripting.repl import REPLPolicy, NTermREPL
from nterm.scripting.repl_interactive import add_repl_to_api

# Convenience: pre-instantiated API
api = get_api()  # <-- This FIRST

# Make api.repl() available
add_repl_to_api(api)  # <-- Then this

__all__ = [
    "NTermAPI",
    "DeviceInfo",
    "CredentialInfo",
    "get_api",
    "reset_api",
    "api",
    'REPLPolicy',
    'NTermREPL'
]