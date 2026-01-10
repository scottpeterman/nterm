"""
nterm - A themeable SSH terminal widget for PyQt6.

Clean architecture with:
- Connection profiles (fully serializable)
- Session management with auto-reconnect
- Jump host / bastion support
- YubiKey/FIDO2 agent auth (native SSH + PTY)
- xterm.js rendering
- Themeable UI

Session types:
- SSHSession: Paramiko-based, programmatic auth
- InteractiveSSHSession: Native ssh with PTY for full interactive auth
- HybridSSHSession: Interactive auth with ControlMaster reuse (Unix only)
"""

__version__ = "0.2.0"
__author__ = "Scott Peterman"

from .connection.profile import (
    ConnectionProfile,
    AuthConfig,
    AuthMethod,
    JumpHostConfig,
)
from .session.base import Session, SessionState
from .session.ssh import SSHSession
from .session.interactive_ssh import InteractiveSSHSession, HybridSSHSession
from .session.pty_transport import is_pty_available, IS_WINDOWS
from .terminal.widget import TerminalWidget
from .theme.engine import Theme, ThemeEngine

__all__ = [
    # Connection
    "ConnectionProfile",
    "AuthConfig", 
    "AuthMethod",
    "JumpHostConfig",
    # Sessions
    "Session",
    "SessionState",
    "SSHSession",
    "InteractiveSSHSession",
    "HybridSSHSession",
    # Utilities
    "is_pty_available",
    "IS_WINDOWS",
    # Terminal
    "TerminalWidget",
    # Themes
    "Theme",
    "ThemeEngine",
]
