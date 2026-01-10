"""
SSH_ASKPASS implementation for GUI-based authentication.

This module provides:
- AskpassServer: Listens for SSH authentication requests
- AskpassRequest/Response: Data structures for the protocol
- BlockingAskpassHandler: Helper for synchronous GUI integration
"""

from .server import (
    AskpassServer,
    AskpassRequest,
    AskpassResponse,
    BlockingAskpassHandler,
)

__all__ = [
    "AskpassServer",
    "AskpassRequest", 
    "AskpassResponse",
    "BlockingAskpassHandler",
]
