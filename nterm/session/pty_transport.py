"""
Cross-platform PTY for interactive terminals.

Provides a unified interface for pseudo-terminal operations
on both Unix (pty module) and Windows (pywinpty/ConPTY).
"""

from __future__ import annotations
import os
import sys
import subprocess
import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)

# Platform detection
IS_WINDOWS = sys.platform == 'win32'

# Try pexpect first on Unix (most reliable for capturing /dev/tty)
HAS_PEXPECT = False
if not IS_WINDOWS:
    try:
        import pexpect
        HAS_PEXPECT = True
    except ImportError:
        logger.info("pexpect not installed - falling back to pty module")

if IS_WINDOWS:
    try:
        from winpty import PTY as WinPTY
        HAS_WINPTY = True
    except ImportError:
        HAS_WINPTY = False
        logger.warning("pywinpty not installed - interactive SSH unavailable on Windows")
else:
    import pty
    import tty
    import fcntl
    import termios
    import struct
    import select
    HAS_WINPTY = False  # Not needed


class PTYTransport(ABC):
    """
    Abstract PTY interface.

    Provides cross-platform pseudo-terminal functionality for
    spawning and interacting with processes that require a TTY.
    """

    @abstractmethod
    def spawn(self, command: list[str], env: dict = None, echo: bool = True) -> None:
        """
        Spawn process with PTY.

        Args:
            command: Command and arguments to execute
            env: Optional environment variables
            echo: Whether to echo input back to terminal. Set False for SSH
                  (remote handles echo), True for local shells/apps.
        """
        pass

    @abstractmethod
    def read(self, size: int = 4096) -> bytes:
        """
        Read from PTY (non-blocking).

        Args:
            size: Maximum bytes to read

        Returns:
            Bytes read, empty if nothing available
        """
        pass

    @abstractmethod
    def write(self, data: bytes) -> int:
        """
        Write to PTY.

        Args:
            data: Bytes to write

        Returns:
            Number of bytes written
        """
        pass

    @abstractmethod
    def resize(self, cols: int, rows: int) -> None:
        """
        Resize PTY.

        Args:
            cols: Number of columns
            rows: Number of rows
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Close PTY and terminate process."""
        pass

    @property
    @abstractmethod
    def is_alive(self) -> bool:
        """Check if process is still running."""
        pass

    @property
    @abstractmethod
    def exit_code(self) -> Optional[int]:
        """Get exit code if process has terminated."""
        pass


class UnixPTY(PTYTransport):
    """
    Unix PTY implementation using subprocess + pty.

    Uses subprocess.Popen with start_new_session=True and preexec_fn
    to properly set up the controlling terminal.
    """

    def __init__(self):
        self._master_fd: Optional[int] = None
        self._proc: Optional[subprocess.Popen] = None
        self._exit_code: Optional[int] = None

    def spawn(self, command: list[str], env: dict = None, echo: bool = True) -> None:
        """Spawn process with PTY using subprocess."""

        # Merge environment
        spawn_env = os.environ.copy()
        if env:
            spawn_env.update(env)
        spawn_env['TERM'] = 'xterm-256color'

        # Create pseudo-terminal pair
        self._master_fd, slave_fd = pty.openpty()
        slave_name = os.ttyname(slave_fd)
        spawn_env['SSH_TTY'] = slave_name

        # Determine TIOCSCTTY value for this platform
        import platform
        if platform.system() == 'Darwin':
            tiocsctty = 0x20007461
        else:
            tiocsctty = 0x540E

        def setup_child():
            """
            Called in child process after fork, before exec.
            Sets up the PTY as the controlling terminal.
            """
            # Close the slave fd we inherited - we'll open it fresh
            try:
                os.close(slave_fd)
            except:
                pass

            # start_new_session=True already called setsid()
            # Now open the slave device fresh - first open after setsid
            # becomes controlling terminal on Linux
            new_slave = os.open(slave_name, os.O_RDWR)

            # Explicitly set as controlling terminal (needed on some systems)
            try:
                fcntl.ioctl(new_slave, tiocsctty, 0)
            except (OSError, IOError):
                pass

            # Redirect stdin/stdout/stderr to the PTY
            os.dup2(new_slave, 0)
            os.dup2(new_slave, 1)
            os.dup2(new_slave, 2)

            if new_slave > 2:
                os.close(new_slave)

        # Spawn the process
        self._proc = subprocess.Popen(
            command,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            start_new_session=True,  # Calls setsid()
            preexec_fn=setup_child,
            env=spawn_env,
            close_fds=True,
        )

        # Close slave in parent
        os.close(slave_fd)

        # Set master to non-blocking
        flags = fcntl.fcntl(self._master_fd, fcntl.F_GETFL)
        fcntl.fcntl(self._master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        logger.debug(f"Spawned PID {self._proc.pid}: {' '.join(command)}")

    def read(self, size: int = 4096) -> bytes:
        """Read from PTY (non-blocking)."""
        if self._master_fd is None:
            return b''

        try:
            # Check if data available
            r, _, _ = select.select([self._master_fd], [], [], 0)
            if not r:
                return b''
            return os.read(self._master_fd, size)
        except (BlockingIOError, InterruptedError):
            return b''
        except OSError as e:
            # EIO typically means child exited
            if e.errno == 5:  # EIO
                self._check_exit()
            return b''

    def write(self, data: bytes) -> int:
        """Write to PTY."""
        if self._master_fd is None:
            return 0
        try:
            return os.write(self._master_fd, data)
        except OSError:
            return 0

    def resize(self, cols: int, rows: int) -> None:
        """Resize PTY using TIOCSWINSZ ioctl."""
        if self._master_fd is not None:
            try:
                winsize = struct.pack('HHHH', rows, cols, 0, 0)
                fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ, winsize)
            except OSError as e:
                logger.warning(f"Resize failed: {e}")

    def close(self) -> None:
        """Close PTY and terminate process."""
        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = None

        if self._proc is not None:
            try:
                self._proc.terminate()  # SIGTERM
            except OSError:
                pass

            # Wait briefly, then force kill
            import time
            for _ in range(10):
                if self._proc.poll() is not None:
                    break
                time.sleep(0.1)

            if self._proc.poll() is None:
                try:
                    self._proc.kill()  # SIGKILL
                except OSError:
                    pass

            self._check_exit()

    def _check_exit(self) -> None:
        """Check and store exit status."""
        if self._proc is not None and self._exit_code is None:
            retcode = self._proc.poll()
            if retcode is not None:
                self._exit_code = retcode

    @property
    def is_alive(self) -> bool:
        """Check if process is still running."""
        if self._proc is None:
            return False

        return self._proc.poll() is None

    @property
    def exit_code(self) -> Optional[int]:
        """Get exit code if process has terminated."""
        self._check_exit()
        return self._exit_code


class WindowsPTY(PTYTransport):
    """
    Windows ConPTY implementation using pywinpty.

    Requires Windows 10 1809+ and pywinpty package.
    """

    def __init__(self):
        if not HAS_WINPTY:
            raise RuntimeError(
                "pywinpty not installed. Install with: pip install pywinpty"
            )
        self._pty = None
        self._exit_code: Optional[int] = None
        self._cols = 120
        self._rows = 40

    def spawn(self, command: list[str], env: dict = None, echo: bool = True) -> None:
        """Spawn process with ConPTY."""
        # pywinpty wants command as string
        cmd_str = subprocess.list2cmdline(command)

        # Merge environment
        spawn_env = os.environ.copy()
        if env:
            spawn_env.update(env)
        spawn_env.setdefault('TERM', 'xterm-256color')

        # Create PTY
        self._pty = WinPTY(
            cols=self._cols,
            rows=self._rows,
        )

        # Spawn process
        # Note: ConPTY handles echo automatically based on the application
        self._pty.spawn(cmd_str, env=spawn_env)
        logger.debug(f"Spawned: {cmd_str}")

    def read(self, size: int = 4096) -> bytes:
        """Read from PTY (non-blocking)."""
        if self._pty is None:
            return b''

        try:
            # pywinpty read with timeout=0 for non-blocking
            data = self._pty.read(size, blocking=False)
            if data:
                # pywinpty returns str, encode to bytes
                if isinstance(data, str):
                    return data.encode('utf-8', errors='replace')
                return data
            return b''
        except Exception as e:
            logger.debug(f"Read error: {e}")
            return b''

    def write(self, data: bytes) -> int:
        """Write to PTY."""
        if self._pty is None:
            return 0

        try:
            # pywinpty expects str
            if isinstance(data, bytes):
                text = data.decode('utf-8', errors='replace')
            else:
                text = data
            self._pty.write(text)
            return len(data)
        except Exception as e:
            logger.debug(f"Write error: {e}")
            return 0

    def resize(self, cols: int, rows: int) -> None:
        """Resize ConPTY."""
        self._cols = cols
        self._rows = rows
        if self._pty is not None:
            try:
                self._pty.set_size(cols, rows)
            except Exception as e:
                logger.warning(f"Resize failed: {e}")

    def close(self) -> None:
        """Close PTY."""
        if self._pty is not None:
            try:
                # Check exit status before closing
                if not self._pty.isalive():
                    self._exit_code = self._pty.get_exitstatus()
                self._pty.close()
            except Exception as e:
                logger.debug(f"Close error: {e}")
            self._pty = None

    @property
    def is_alive(self) -> bool:
        """Check if process is still running."""
        if self._pty is None:
            return False
        try:
            alive = self._pty.isalive()
            if not alive and self._exit_code is None:
                self._exit_code = self._pty.get_exitstatus()
            return alive
        except:
            return False

    @property
    def exit_code(self) -> Optional[int]:
        """Get exit code if process has terminated."""
        if self._exit_code is None and self._pty is not None:
            if not self.is_alive:
                try:
                    self._exit_code = self._pty.get_exitstatus()
                except:
                    pass
        return self._exit_code


class PexpectPTY(PTYTransport):
    """
    PTY implementation using pexpect.

    pexpect is specifically designed to handle interactive programs
    and properly captures /dev/tty output. This is the most reliable
    method for capturing SSH keyboard-interactive prompts, YubiKey
    challenges, etc.

    Requires: pip install pexpect
    """

    def __init__(self):
        if not HAS_PEXPECT:
            raise RuntimeError(
                "pexpect not installed. Install with: pip install pexpect"
            )
        self._child: Optional[pexpect.spawn] = None
        self._exit_code: Optional[int] = None
        self._cols = 120
        self._rows = 40

    def spawn(self, command: list[str], env: dict = None, echo: bool = True) -> None:
        """
        Spawn process using pexpect.

        Args:
            command: Command and arguments to execute
            env: Optional environment variables
            echo: Whether PTY should echo input. Set False for SSH (remote
                  PTY handles echo), True for local shells and applications
                  like vim that need to see their own input.
        """
        # Merge environment
        spawn_env = os.environ.copy()
        if env:
            spawn_env.update(env)
        spawn_env['TERM'] = 'xterm-256color'

        # pexpect.spawn takes command as string or list
        # Using list form for proper argument handling
        cmd = command[0]
        args = command[1:] if len(command) > 1 else []

        self._child = pexpect.spawn(
            cmd,
            args=args,
            env=spawn_env,
            encoding=None,  # Binary mode
            dimensions=(self._rows, self._cols),
        )

        # Control echo based on use case:
        # - SSH: echo=False (remote PTY handles echo)
        # - Local shell/apps: echo=True (local PTY must echo)
        self._child.setecho(echo)

        logger.debug(f"Spawned via pexpect (echo={echo}): {' '.join(command)}")

    def read(self, size: int = 4096) -> bytes:
        """Read from PTY (non-blocking)."""
        if self._child is None:
            return b''

        try:
            # Use read_nonblocking for non-blocking read
            data = self._child.read_nonblocking(size, timeout=0)
            return data if data else b''
        except pexpect.TIMEOUT:
            return b''
        except pexpect.EOF:
            self._check_exit()
            return b''
        except Exception as e:
            logger.debug(f"Read error: {e}")
            return b''

    def write(self, data: bytes) -> int:
        """Write to PTY."""
        if self._child is None:
            return 0

        try:
            self._child.send(data)
            return len(data)
        except Exception as e:
            logger.debug(f"Write error: {e}")
            return 0

    def resize(self, cols: int, rows: int) -> None:
        """Resize PTY."""
        self._cols = cols
        self._rows = rows
        if self._child is not None:
            try:
                self._child.setwinsize(rows, cols)
            except Exception as e:
                logger.warning(f"Resize failed: {e}")

    def close(self) -> None:
        """Close PTY and terminate process."""
        if self._child is not None:
            try:
                self._child.close(force=True)
            except Exception as e:
                logger.debug(f"Close error: {e}")
            self._check_exit()
            self._child = None

    def _check_exit(self) -> None:
        """Check and store exit status."""
        if self._child is not None and self._exit_code is None:
            if not self._child.isalive():
                self._exit_code = self._child.exitstatus
                if self._exit_code is None:
                    self._exit_code = self._child.signalstatus or -1

    @property
    def is_alive(self) -> bool:
        """Check if process is still running."""
        if self._child is None:
            return False
        alive = self._child.isalive()
        if not alive:
            self._check_exit()
        return alive

    @property
    def exit_code(self) -> Optional[int]:
        """Get exit code if process has terminated."""
        self._check_exit()
        return self._exit_code


def create_pty(use_pexpect: bool = True) -> PTYTransport:
    """
    Factory for platform-appropriate PTY.

    Args:
        use_pexpect: If True and pexpect is available, use PexpectPTY (recommended)

    Returns:
        PTYTransport instance for current platform

    Raises:
        RuntimeError: If PTY support not available
    """
    if IS_WINDOWS:
        if not HAS_WINPTY:
            raise RuntimeError(
                "pywinpty required for Windows. Install with: pip install pywinpty"
            )
        return WindowsPTY()

    # On Unix, prefer pexpect for best /dev/tty capture
    if use_pexpect and HAS_PEXPECT:
        logger.debug("Using PexpectPTY for best /dev/tty capture")
        return PexpectPTY()

    logger.debug("Using UnixPTY")
    return UnixPTY()


def is_pty_available() -> bool:
    """Check if PTY support is available on current platform."""
    if IS_WINDOWS:
        return HAS_WINPTY
    return True  # Always available on Unix