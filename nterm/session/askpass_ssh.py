"""
SSH session using SSH_ASKPASS for GUI-based authentication.

This session type uses the native ssh binary with SSH_ASKPASS to capture
all authentication prompts (passwords, YubiKey touches, MFA) and route
them to the GUI application.

This is the recommended approach for GUI applications as it uses the
official SSH mechanism for non-terminal authentication rather than
trying to capture /dev/tty.
"""

from __future__ import annotations
import os
import shutil
import subprocess
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
from ..askpass import AskpassServer, AskpassRequest, AskpassResponse, BlockingAskpassHandler

logger = logging.getLogger(__name__)


class AskpassSSHSession(Session):
    """
    SSH session using SSH_ASKPASS for authentication prompts.
    
    This session type uses the SSH_ASKPASS mechanism to capture
    authentication prompts and route them to the GUI. This is how
    tools like git-gui, seahorse, and ksshaskpass handle SSH auth.
    
    Features:
    - Password prompts appear in GUI
    - YubiKey/FIDO2 touch prompts appear in GUI
    - Keyboard-interactive MFA prompts appear in GUI
    - SSH banners displayed in terminal
    - ProxyJump for jump hosts
    
    The session emits InteractionRequired events when SSH needs input.
    The application must respond by calling provide_askpass_response().
    
    Works on:
    - Linux/macOS: Full support
    - Windows: Requires pywinpty
    """
    
    def __init__(self, profile: ConnectionProfile):
        """
        Initialize askpass SSH session.
        
        Args:
            profile: Connection profile with host and auth info
        """
        self.profile = profile
        
        self._state = SessionState.DISCONNECTED
        self._state_lock = threading.Lock()
        
        self._pty: Optional[PTYTransport] = None
        self._stop_event = threading.Event()
        self._event_handler: Optional[Callable[[SessionEvent], None]] = None
        
        self._cols = profile.term_cols
        self._rows = profile.term_rows
        
        self._reconnect_attempt = 0
        
        # Askpass components
        self._askpass_server: Optional[AskpassServer] = None
        self._askpass_handler: Optional[BlockingAskpassHandler] = None
    
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
        
        # Start askpass server
        self._start_askpass_server()
        
        self._stop_event.clear()
        thread = threading.Thread(target=self._connect_thread, daemon=True)
        thread.start()
    
    def _start_askpass_server(self) -> None:
        """Start the askpass server for handling auth prompts."""
        self._askpass_handler = BlockingAskpassHandler()
        self._askpass_handler.on_request = self._on_askpass_request
        
        self._askpass_server = AskpassServer()
        self._askpass_server.set_handler(self._askpass_handler.handle_request)
        self._askpass_server.start()
        
        logger.info("Askpass server started")
    
    def _stop_askpass_server(self) -> None:
        """Stop the askpass server."""
        if self._askpass_server:
            self._askpass_server.stop()
            self._askpass_server = None
        self._askpass_handler = None
    
    def _on_askpass_request(self, request: AskpassRequest) -> None:
        """
        Called when SSH needs authentication input.
        Emits InteractionRequired event to the GUI.
        """
        # Determine interaction type
        if request.is_confirmation:
            interaction_type = "yubikey_touch"
        elif request.is_password:
            interaction_type = "password"
        else:
            interaction_type = "input"
        
        logger.info(f"Askpass request: {request.prompt} (type={interaction_type})")
        
        # Emit event to GUI
        self._emit(InteractionRequired(request.prompt, interaction_type))
    
    def provide_askpass_response(self, success: bool, value: str = "", error: str = "") -> None:
        """
        Provide response to pending askpass request.
        
        Call this from the GUI when user provides input or touches YubiKey.
        
        Args:
            success: True if user provided input, False if cancelled
            value: The password/input value (empty for YubiKey touch)
            error: Error message if not successful
        """
        if self._askpass_handler:
            self._askpass_handler.provide_response(success, value, error)
    
    def cancel_askpass(self) -> None:
        """Cancel pending askpass request."""
        if self._askpass_handler:
            self._askpass_handler.cancel()
    
    def _find_ssh(self) -> Optional[str]:
        """Find ssh executable in PATH."""
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
                    '-o', 'PreferredAuthentications=publickey',
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
            
            # Build environment with askpass
            env = os.environ.copy()
            env['TERM'] = 'xterm-256color'
            
            if self._askpass_server:
                env.update(self._askpass_server.get_env())
                logger.info(f"SSH_ASKPASS={env.get('SSH_ASKPASS')}")
            
            # Create PTY and spawn SSH
            self._pty = create_pty(use_pexpect=False)  # Don't use pexpect with askpass
            self._pty.spawn(cmd, env=env)
            self._pty.resize(self._cols, self._rows)
            
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
                self._start_askpass_server()  # Restart askpass server
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
        """Clean up PTY and askpass server."""
        if self._pty:
            try:
                self._pty.close()
            except Exception as e:
                logger.debug(f"PTY cleanup error: {e}")
            self._pty = None
        
        self._stop_askpass_server()
