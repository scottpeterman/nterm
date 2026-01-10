"""
Terminal widget - PyQt6 + xterm.js rendering.
"""

from .widget import TerminalWidget
from .bridge import TerminalBridge

__all__ = [
    "TerminalWidget",
    "TerminalBridge",
]
