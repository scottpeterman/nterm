"""
Standalone local terminal session.
Minimal Session-compatible wrapper for local PTY processes.
"""

import sys
import os
import threading
import time
import logging
from typing import Optional, Callable, List

from .pty_transport import create_pty, is_pty_available, PTYTransport
from .base import SessionState, SessionEvent, DataReceived, StateChanged

logger = logging.getLogger(__name__)


# IPython startup code to inject the nterm API
IPYTHON_STARTUP = '''
from nterm.scripting import api
print("\\n\\033[1;36mnterm API loaded.\\033[0m")
print("  api.devices()      - List saved devices")
print("  api.search(query)  - Search devices")  
print("  api.credentials()  - List credentials (after api.unlock())")
print("  api.help()         - Show all commands")
print()
'''


class LocalTerminal:
    """
    Lightweight local PTY session.

    Implements just enough of Session interface for TerminalWidget.
    Completely separate from SSH session management.

    Usage:
        # Default shell
        session = LocalTerminal()

        # IPython with nterm API pre-loaded
        session = LocalTerminal.ipython()

        # Python REPL
        session = LocalTerminal.python()

        # Arbitrary command
        session = LocalTerminal(['htop'])
    """

    def __init__(self, command: Optional[List[str]] = None):
        """
        Initialize local terminal session.

        Args:
            command: Command to run. Defaults to user's shell.
        """
        self._command = command or self._default_shell()
        self._pty: Optional[PTYTransport] = None
        self._state = SessionState.DISCONNECTED
        self._stop = threading.Event()
        self._handler: Optional[Callable[[SessionEvent], None]] = None
        self._cols, self._rows = 120, 40

    @staticmethod
    def _default_shell() -> List[str]:
        """Get user's default shell."""
        if sys.platform == 'win32':
            return [os.environ.get('COMSPEC', 'cmd.exe')]
        return [os.environ.get('SHELL', '/bin/bash')]

    @classmethod
    def ipython(cls, with_api: bool = True) -> 'LocalTerminal':
        """
        Create IPython session in current venv.

        Args:
            with_api: If True, pre-load nterm scripting API into namespace

        Returns:
            LocalTerminal configured to run IPython

        Raises:
            RuntimeError: If IPython is not installed
        """
        try:
            import IPython  # noqa: F401
        except ImportError:
            raise RuntimeError(
                "IPython not installed. Install with: pip install ntermqt[scripting]"
            )

        if with_api:
            # Use -i with -c to run startup code then go interactive
            cmd = [
                sys.executable, '-m', 'IPython',
                '-i', '-c', IPYTHON_STARTUP
            ]
        else:
            cmd = [sys.executable, '-m', 'IPython']
        return cls(cmd)

    @classmethod
    def python(cls) -> 'LocalTerminal':
        """
        Create Python REPL session in current venv.

        Returns:
            LocalTerminal configured to run Python
        """
        return cls([sys.executable])

    @classmethod
    def shell(cls, shell: str = None) -> 'LocalTerminal':
        """
        Create shell session.

        Args:
            shell: Optional shell path. Defaults to user's default shell.

        Returns:
            LocalTerminal configured to run shell
        """
        if shell:
            return cls([shell])
        return cls()

    # -------------------------------------------------------------------------
    # Session interface (minimal subset for TerminalWidget compatibility)
    # -------------------------------------------------------------------------

    @property
    def state(self) -> SessionState:
        """Current session state."""
        return self._state

    @property
    def is_connected(self) -> bool:
        """Check if process is running."""
        return self._state == SessionState.CONNECTED

    def set_event_handler(self, handler: Callable[[SessionEvent], None]) -> None:
        """Set callback for session events."""
        self._handler = handler

    def set_auto_reconnect(self, enabled: bool) -> None:
        """No-op for local sessions."""
        pass

    def connect(self) -> None:
        """Start the local process."""
        if not is_pty_available():
            self._set_state(SessionState.FAILED, "PTY unavailable. On Windows, install pywinpty.")
            return
        self._stop.clear()
        threading.Thread(target=self._run, daemon=True).start()

    def write(self, data: bytes) -> None:
        """Send input to process."""
        if self._pty:
            self._pty.write(data)

    def resize(self, cols: int, rows: int) -> None:
        """Resize terminal."""
        self._cols, self._rows = cols, rows
        if self._pty:
            self._pty.resize(cols, rows)

    def disconnect(self) -> None:
        """Terminate the process."""
        self._stop.set()
        if self._pty:
            self._pty.close()
            self._pty = None
        self._set_state(SessionState.DISCONNECTED, "Closed")

    # -------------------------------------------------------------------------
    # Internal
    # -------------------------------------------------------------------------

    def _set_state(self, state: SessionState, msg: str = ""):
        """Update state and notify handler."""
        old, self._state = self._state, state
        logger.debug(f"LocalTerminal: {old.name} -> {state.name} {msg}")
        if self._handler:
            try:
                self._handler(StateChanged(old, state, msg))
            except Exception as e:
                logger.exception(f"Event handler error: {e}")

    def _run(self):
        """Main PTY read loop (runs in thread)."""
        try:
            self._set_state(SessionState.CONNECTING)

            logger.info(f"Spawning: {' '.join(self._command)}")

            self._pty = create_pty()
            self._pty.spawn(self._command, echo=True)  # Local apps need echo
            self._pty.resize(self._cols, self._rows)

            self._set_state(SessionState.CONNECTED)

            # Read loop
            while not self._stop.is_set() and self._pty.is_alive:
                data = self._pty.read(8192)
                if data and self._handler:
                    self._handler(DataReceived(data))
                else:
                    time.sleep(0.01)

            # Process exited
            if not self._stop.is_set():
                exit_code = self._pty.exit_code if self._pty else None
                msg = f"Process exited (code {exit_code})" if exit_code is not None else "Process exited"
                self._set_state(SessionState.DISCONNECTED, msg)

        except Exception as e:
            logger.exception("LocalTerminal failed")
            self._set_state(SessionState.FAILED, str(e))
        finally:
            if self._pty:
                self._pty.close()
                self._pty = None