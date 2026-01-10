"""
Session management - handles connection lifecycle and I/O.

Provides multiple session implementations:

- SSHSession: Paramiko-based, programmatic auth (password, key, agent)
- InteractiveSSHSession: Native ssh binary with PTY for full interactive auth
- AskpassSSHSession: Native ssh with SSH_ASKPASS for GUI prompts (recommended)
- HybridSSHSession: Interactive auth with ControlMaster for connection reuse

Choose based on your needs:
- Use SSHSession for automation with stored credentials
- Use AskpassSSHSession for GUI apps with YubiKey/MFA (recommended)
- Use InteractiveSSHSession for console-like terminal experience
- Use HybridSSHSession for interactive auth followed by programmatic control

For best results with GUI authentication, use AskpassSSHSession.
"""

from .base import (
    Session,
    SessionState,
    SessionEvent,
    DataReceived,
    StateChanged,
    InteractionRequired,
    BannerReceived,
)
from .ssh import SSHSession
from .interactive_ssh import InteractiveSSHSession, HybridSSHSession
from .askpass_ssh import AskpassSSHSession
from .pty_transport import (
    PTYTransport,
    create_pty,
    is_pty_available,
    IS_WINDOWS,
    HAS_PEXPECT,
)

__all__ = [
    # Base classes
    "Session",
    "SessionState",
    "SessionEvent",
    "DataReceived",
    "StateChanged",
    "InteractionRequired",
    "BannerReceived",
    # Session implementations
    "SSHSession",
    "InteractiveSSHSession",
    "AskpassSSHSession",
    "HybridSSHSession",
    # PTY support
    "PTYTransport",
    "create_pty",
    "is_pty_available",
    "IS_WINDOWS",
    "HAS_PEXPECT",
]
