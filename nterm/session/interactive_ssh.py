"""
Interactive SSH session using native ssh binary.

Uses the system's ssh client for full interactive authentication support,
including YubiKey/FIDO2 prompts, keyboard-interactive auth, and banners.
Works on both Unix and Windows (with OpenSSH installed).
"""

from __future__ import annotations
import os
import shutil
import threading
import time
import logging
from typing import Optional, Callable
from pathlib import Path

from .base import (
    Session, SessionState, SessionEvent,
    DataReceived, StateChanged, InteractionRequired
)
from .pty_transport import create_pty, is_pty_available, PTYTransport, IS_WINDOWS
from ..connection.profile import ConnectionProfile, AuthMethod

logger = logging.getLogger(__name__)


class InteractiveSSHSession(Session):
    """
    SSH session using native ssh binary with PTY.
    
    This session type spawns the system's ssh client in a pseudo-terminal,
    providing full interactive authentication support including:
    
    - SSH agent authentication (YubiKey touch prompts visible)
    - Keyboard-interactive authentication (MFA prompts)
    - Full banner display
    - ProxyJump for jump hosts
    
    Works on:
    - Linux/macOS: Uses pty module
    - Windows 10+: Uses pywinpty (ConPTY)
    
    Requirements:
    - ssh binary in PATH (OpenSSH)
    - pywinpty package on Windows
    """
    
    def __init__(self, profile: ConnectionProfile):
        """
        Initialize interactive SSH session.
        
        Args:
            profile: Connection profile with host and auth info
        """
        self.profile = profile
        
        self._state = SessionState.DISCONNECTED
        self._state_lock = threading.Lock()
        
        self._pty: Optional[PTYTransport] = None
        self._read_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._event_handler: Optional[Callable[[SessionEvent], None]] = None
        
        self._cols = profile.term_cols
        self._rows = profile.term_rows
        
        self._reconnect_attempt = 0
    
    @property
    def state(self) -> SessionState:
        """Current session state."""
        with self._state_lock:
            return self._state
    
    @property
    def is_connected(self) -> bool:
        """Is session currently connected and usable?"""
        return self.state == SessionState.CONNECTED
    
    def set_event_handler(self, handler: Callable[[SessionEvent], None]) -> None:
        """Set callback for session events."""
        self._event_handler = handler
    
    def _emit(self, event: SessionEvent) -> None:
        """Emit event to handler."""
        if self._event_handler:
            try:
                self._event_handler(event)
            except Exception as e:
                logger.exception(f"Event handler error: {e}")
    
    def _set_state(self, new_state: SessionState, message: str = "") -> None:
        """Update state and emit event."""
        with self._state_lock:
            old_state = self._state
            self._state = new_state
        logger.info(f"Session state: {old_state.name} -> {new_state.name} {message}")
        self._emit(StateChanged(old_state, new_state, message))
    
    def connect(self) -> None:
        """Start SSH connection."""
        if self.state not in (SessionState.DISCONNECTED, SessionState.FAILED):
            logger.warning(f"Cannot connect from state {self.state}")
            return
        
        # Check prerequisites
        if not is_pty_available():
            self._set_state(
                SessionState.FAILED, 
                "PTY not available. On Windows, install pywinpty."
            )
            return
        
        ssh_path = self._find_ssh()
        if not ssh_path:
            self._set_state(
                SessionState.FAILED,
                "SSH not found. Please install OpenSSH."
            )
            return
        
        self._stop_event.clear()
        thread = threading.Thread(target=self._connect_thread, daemon=True)
        thread.start()
    
    def _find_ssh(self) -> Optional[str]:
        """Find ssh executable in PATH."""
        # On Windows, might be ssh.exe
        names = ['ssh.exe', 'ssh'] if IS_WINDOWS else ['ssh']
        
        for name in names:
            path = shutil.which(name)
            if path:
                logger.debug(f"Found SSH: {path}")
                return path
        
        # Check common Windows locations
        if IS_WINDOWS:
            common_paths = [
                Path(os.environ.get('SystemRoot', 'C:\\Windows')) / 'System32' / 'OpenSSH' / 'ssh.exe',
                Path(os.environ.get('ProgramFiles', 'C:\\Program Files')) / 'OpenSSH' / 'ssh.exe',
                Path(os.environ.get('ProgramFiles', 'C:\\Program Files')) / 'Git' / 'usr' / 'bin' / 'ssh.exe',
            ]
            for p in common_paths:
                if p.exists():
                    logger.debug(f"Found SSH: {p}")
                    return str(p)
        
        return None
    
    def _build_ssh_command(self) -> list[str]:
        """Build ssh command with options from profile."""
        cmd = ['ssh']
        
        # Force PTY allocation
        cmd.append('-tt')
        
        # Jump hosts via ProxyJump
        if self.profile.jump_hosts:
            jump_specs = []
            for jump in self.profile.jump_hosts:
                if jump.auth and jump.auth.username:
                    spec = f"{jump.auth.username}@{jump.hostname}"
                else:
                    spec = jump.hostname
                if jump.port != 22:
                    spec += f":{jump.port}"
                jump_specs.append(spec)
            
            cmd.extend(['-J', ','.join(jump_specs)])
        
        # Connection options
        cmd.extend([
            '-o', 'StrictHostKeyChecking=accept-new',
            '-o', f'ConnectTimeout={int(self.profile.connect_timeout)}',
            '-o', f'ServerAliveInterval={self.profile.keepalive_interval}',
            '-o', f'ServerAliveCountMax={self.profile.keepalive_count_max}',
        ])
        
        # Handle specific auth methods
        if self.profile.auth_methods:
            auth = self.profile.auth_methods[0]
            
            # Key file if specified
            if auth.method == AuthMethod.KEY_FILE and auth.key_path:
                cmd.extend(['-i', auth.key_path])
            
            # Disable password auth if using agent/key only
            if auth.method == AuthMethod.AGENT:
                cmd.extend([
                    '-o', 'PasswordAuthentication=no',
                    '-o', 'PreferredAuthentications=publickey',
                ])
            elif auth.method == AuthMethod.PASSWORD:
                # For password auth, we'd need sshpass or expect
                # Just let SSH prompt - user can type password
                cmd.extend([
                    '-o', 'PreferredAuthentications=keyboard-interactive,password',
                ])
        
        # Port if non-standard
        if self.profile.port != 22:
            cmd.extend(['-p', str(self.profile.port)])
        
        # Build user@host
        if self.profile.auth_methods and self.profile.auth_methods[0].username:
            username = self.profile.auth_methods[0].username
            cmd.append(f'{username}@{self.profile.hostname}')
        else:
            cmd.append(self.profile.hostname)
        
        return cmd
    
    def _connect_thread(self) -> None:
        """Connection thread - spawns ssh and handles I/O."""
        try:
            self._set_state(SessionState.CONNECTING)
            
            # Build command
            cmd = self._build_ssh_command()
            logger.info(f"SSH command: {' '.join(cmd)}")
            
            # Create PTY and spawn SSH
            self._pty = create_pty()
            self._pty.spawn(cmd)
            self._pty.resize(self._cols, self._rows)
            
            # Note: We go straight to CONNECTED because the terminal
            # will show the authentication prompts interactively
            self._set_state(SessionState.CONNECTED)
            self._reconnect_attempt = 0
            
            # Read loop
            self._read_loop()
            
        except Exception as e:
            logger.exception("Connection failed")
            self._cleanup()
            self._set_state(SessionState.FAILED, str(e))
            
            if self.profile.auto_reconnect and not self._stop_event.is_set():
                self._schedule_reconnect()
    
    def _read_loop(self) -> None:
        """Read from PTY and emit data events."""
        while not self._stop_event.is_set():
            if not self._pty:
                break
            
            if not self._pty.is_alive:
                exit_code = self._pty.exit_code
                logger.info(f"SSH process exited with code {exit_code}")
                break
            
            data = self._pty.read(8192)
            if data:
                self._emit(DataReceived(data))
            else:
                # No data, small sleep to avoid busy-wait
                time.sleep(0.01)
        
        # Connection ended
        if not self._stop_event.is_set():
            exit_code = self._pty.exit_code if self._pty else None
            self._cleanup()
            
            if exit_code == 0:
                self._set_state(SessionState.DISCONNECTED, "Connection closed")
            else:
                self._set_state(
                    SessionState.DISCONNECTED, 
                    f"SSH exited with code {exit_code}"
                )
            
            if self.profile.auto_reconnect:
                self._schedule_reconnect()
    
    def _schedule_reconnect(self) -> None:
        """Schedule a reconnection attempt."""
        if self._reconnect_attempt >= self.profile.reconnect_max_attempts:
            self._set_state(SessionState.FAILED, "Max reconnection attempts reached")
            return
        
        delay = self.profile.reconnect_delay * (
            self.profile.reconnect_backoff ** self._reconnect_attempt
        )
        self._reconnect_attempt += 1
        
        self._set_state(
            SessionState.RECONNECTING,
            f"Reconnecting in {delay:.1f}s (attempt {self._reconnect_attempt})"
        )
        
        def reconnect():
            time.sleep(delay)
            if not self._stop_event.is_set():
                self._connect_thread()
        
        thread = threading.Thread(target=reconnect, daemon=True)
        thread.start()
    
    def write(self, data: bytes) -> None:
        """Send data to SSH process."""
        if self._pty:
            self._pty.write(data)
    
    def resize(self, cols: int, rows: int) -> None:
        """Resize terminal."""
        self._cols = cols
        self._rows = rows
        if self._pty:
            self._pty.resize(cols, rows)
    
    def disconnect(self) -> None:
        """Disconnect session."""
        logger.info("Disconnecting...")
        self._stop_event.set()
        self._cleanup()
        self._set_state(SessionState.DISCONNECTED, "User disconnected")
    
    def _cleanup(self) -> None:
        """Clean up PTY."""
        if self._pty:
            try:
                self._pty.close()
            except Exception as e:
                logger.debug(f"Cleanup error: {e}")
            self._pty = None


class HybridSSHSession(Session):
    """
    Hybrid session: Interactive auth, then Paramiko for programmatic control.
    
    Uses native SSH with ControlMaster for initial authentication,
    then subsequent connections reuse the authenticated socket.
    
    Benefits:
    - Full interactive auth (YubiKey, MFA, banners)
    - Programmatic control after authentication
    - Connection multiplexing
    
    Note: ControlMaster is Unix-only.
    """
    
    def __init__(self, profile: ConnectionProfile):
        self.profile = profile
        
        self._state = SessionState.DISCONNECTED
        self._pty: Optional[PTYTransport] = None
        self._control_path: Optional[str] = None
        self._event_handler: Optional[Callable[[SessionEvent], None]] = None
        self._stop_event = threading.Event()
        
        self._cols = profile.term_cols
        self._rows = profile.term_rows
    
    @property
    def state(self) -> SessionState:
        return self._state
    
    @property
    def is_connected(self) -> bool:
        return self._state == SessionState.CONNECTED
    
    def set_event_handler(self, handler: Callable[[SessionEvent], None]) -> None:
        self._event_handler = handler
    
    def _emit(self, event: SessionEvent) -> None:
        if self._event_handler:
            self._event_handler(event)
    
    def _set_state(self, new_state: SessionState, message: str = "") -> None:
        old_state = self._state
        self._state = new_state
        self._emit(StateChanged(old_state, new_state, message))
    
    def connect(self) -> None:
        """Start connection with ControlMaster."""
        if IS_WINDOWS:
            self._set_state(
                SessionState.FAILED,
                "HybridSSHSession requires Unix (ControlMaster not available on Windows)"
            )
            return
        
        self._stop_event.clear()
        thread = threading.Thread(target=self._connect_thread, daemon=True)
        thread.start()
    
    def _connect_thread(self) -> None:
        """Connection thread."""
        try:
            self._set_state(SessionState.CONNECTING)
            
            # Create control socket path
            self._control_path = f"/tmp/nterm-{os.getpid()}-{self.profile.hostname}"
            
            # Build SSH command with ControlMaster
            cmd = self._build_control_command()
            logger.info(f"SSH command: {' '.join(cmd)}")
            
            # Spawn
            self._pty = create_pty()
            self._pty.spawn(cmd)
            self._pty.resize(self._cols, self._rows)
            
            self._set_state(SessionState.CONNECTED)
            
            # Read loop
            self._read_loop()
            
        except Exception as e:
            logger.exception("Connection failed")
            self._cleanup()
            self._set_state(SessionState.FAILED, str(e))
    
    def _build_control_command(self) -> list[str]:
        """Build SSH command with ControlMaster."""
        cmd = ['ssh', '-tt']
        
        # ControlMaster settings
        cmd.extend([
            '-o', 'ControlMaster=auto',
            '-o', f'ControlPath={self._control_path}',
            '-o', 'ControlPersist=600',  # Keep socket for 10 minutes
        ])
        
        # Jump hosts
        if self.profile.jump_hosts:
            jump_specs = []
            for jump in self.profile.jump_hosts:
                if jump.auth and jump.auth.username:
                    spec = f"{jump.auth.username}@{jump.hostname}"
                else:
                    spec = jump.hostname
                if jump.port != 22:
                    spec += f":{jump.port}"
                jump_specs.append(spec)
            cmd.extend(['-J', ','.join(jump_specs)])
        
        # Standard options
        cmd.extend([
            '-o', 'StrictHostKeyChecking=accept-new',
            '-o', f'ConnectTimeout={int(self.profile.connect_timeout)}',
        ])
        
        # Port
        if self.profile.port != 22:
            cmd.extend(['-p', str(self.profile.port)])
        
        # User@host
        if self.profile.auth_methods:
            username = self.profile.auth_methods[0].username
            cmd.append(f'{username}@{self.profile.hostname}')
        else:
            cmd.append(self.profile.hostname)
        
        return cmd
    
    def _read_loop(self) -> None:
        """Read loop."""
        while not self._stop_event.is_set():
            if not self._pty or not self._pty.is_alive:
                break
            
            data = self._pty.read(8192)
            if data:
                self._emit(DataReceived(data))
            else:
                time.sleep(0.01)
        
        if not self._stop_event.is_set():
            self._cleanup()
            self._set_state(SessionState.DISCONNECTED, "Connection closed")
    
    def open_channel(self, hostname: str, port: int = 22) -> Optional[object]:
        """
        Open a new channel through the ControlMaster socket.
        
        This can be used to create additional connections without
        re-authenticating.
        
        Returns a Paramiko-compatible channel or None.
        """
        if not self._control_path or not os.path.exists(self._control_path):
            logger.error("ControlMaster socket not available")
            return None
        
        # Would use Paramiko with ProxyCommand here
        # For now, this is a placeholder
        logger.info(f"Would open channel to {hostname}:{port} via {self._control_path}")
        return None
    
    def write(self, data: bytes) -> None:
        if self._pty:
            self._pty.write(data)
    
    def resize(self, cols: int, rows: int) -> None:
        self._cols = cols
        self._rows = rows
        if self._pty:
            self._pty.resize(cols, rows)
    
    def disconnect(self) -> None:
        self._stop_event.set()
        self._cleanup()
        self._set_state(SessionState.DISCONNECTED, "User disconnected")
    
    def _cleanup(self) -> None:
        if self._pty:
            self._pty.close()
            self._pty = None
        
        # Clean up control socket
        if self._control_path and os.path.exists(self._control_path):
            try:
                os.remove(self._control_path)
            except:
                pass
