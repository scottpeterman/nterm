"""
SSH_ASKPASS server for GUI-based SSH authentication.

This module implements the SSH_ASKPASS protocol to capture authentication
prompts (passwords, YubiKey touch requests, etc.) and route them to the GUI.

How it works:
1. AskpassServer listens on a Unix socket
2. SSH_ASKPASS env var points to our helper script
3. When SSH needs input, it calls the helper
4. Helper connects to socket, sends prompt
5. Server emits signal to GUI
6. GUI responds (user types password or touches YubiKey)
7. Response sent back through socket to helper
8. Helper prints response to stdout for SSH
"""

from __future__ import annotations
import os
import sys
import socket
import threading
import tempfile
import json
import logging
import stat
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Path to the helper script (will be created alongside this module)
HELPER_SCRIPT_NAME = "nterm_askpass_helper.py"


@dataclass
class AskpassRequest:
    """Request from SSH for user input."""
    prompt: str
    is_password: bool  # True if input should be hidden
    is_confirmation: bool  # True if just needs confirmation (YubiKey touch)


@dataclass 
class AskpassResponse:
    """Response to send back to SSH."""
    success: bool
    value: str = ""  # Password or empty for confirmation
    error: str = ""


class AskpassServer:
    """
    Server that handles SSH_ASKPASS requests.
    
    Usage:
        server = AskpassServer()
        server.set_handler(my_callback)  # Called when SSH needs input
        server.start()
        
        # Use server.socket_path and server.helper_path in SSH environment
        env = server.get_env()
        
        # ... run SSH ...
        
        server.stop()
    """
    
    def __init__(self):
        self._socket_path: Optional[str] = None
        self._helper_path: Optional[str] = None
        self._server_socket: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._handler: Optional[Callable[[AskpassRequest], AskpassResponse]] = None
        self._temp_dir: Optional[tempfile.TemporaryDirectory] = None
    
    @property
    def socket_path(self) -> Optional[str]:
        """Path to the Unix socket."""
        return self._socket_path
    
    @property
    def helper_path(self) -> Optional[str]:
        """Path to the askpass helper script."""
        return self._helper_path
    
    def set_handler(self, handler: Callable[[AskpassRequest], AskpassResponse]) -> None:
        """
        Set the callback for handling askpass requests.
        
        The handler receives an AskpassRequest and should return an AskpassResponse.
        This will typically show a dialog or terminal prompt in the GUI.
        """
        self._handler = handler
    
    def start(self) -> None:
        """Start the askpass server."""
        if self._running:
            return
        
        # Create temp directory for socket and helper
        self._temp_dir = tempfile.TemporaryDirectory(prefix="nterm_askpass_")
        temp_path = Path(self._temp_dir.name)
        
        # Create Unix socket
        self._socket_path = str(temp_path / "askpass.sock")
        self._server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_socket.bind(self._socket_path)
        self._server_socket.listen(5)
        self._server_socket.settimeout(1.0)  # Allow periodic check for shutdown
        
        # Create helper script
        self._helper_path = str(temp_path / HELPER_SCRIPT_NAME)
        self._create_helper_script()
        
        # Start server thread
        self._running = True
        self._thread = threading.Thread(target=self._server_loop, daemon=True)
        self._thread.start()
        
        logger.info(f"Askpass server started: {self._socket_path}")
    
    def stop(self) -> None:
        """Stop the askpass server."""
        self._running = False
        
        if self._server_socket:
            try:
                self._server_socket.close()
            except:
                pass
            self._server_socket = None
        
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        
        if self._temp_dir:
            try:
                self._temp_dir.cleanup()
            except:
                pass
            self._temp_dir = None
        
        self._socket_path = None
        self._helper_path = None
        
        logger.info("Askpass server stopped")
    
    def get_env(self) -> dict:
        """
        Get environment variables to set for SSH.
        
        Returns dict with SSH_ASKPASS, SSH_ASKPASS_REQUIRE, and NTERM_ASKPASS_SOCK.
        """
        if not self._running:
            raise RuntimeError("Askpass server not running")
        
        return {
            'SSH_ASKPASS': self._helper_path,
            'SSH_ASKPASS_REQUIRE': 'force',  # Use askpass even with TTY
            'NTERM_ASKPASS_SOCK': self._socket_path,
            'DISPLAY': os.environ.get('DISPLAY', ':0'),  # Required for SSH_ASKPASS
        }
    
    def _create_helper_script(self) -> None:
        """Create the askpass helper script."""
        script = f'''#!/usr/bin/env python3
"""
SSH_ASKPASS helper script - communicates with nterm askpass server.
This script is called by SSH when it needs user input.
"""
import os
import sys
import socket
import json

def main():
    # Get prompt from command line (SSH passes it as argv[1])
    prompt = sys.argv[1] if len(sys.argv) > 1 else "Password: "
    
    # Get socket path from environment
    sock_path = os.environ.get('NTERM_ASKPASS_SOCK')
    if not sock_path:
        print("NTERM_ASKPASS_SOCK not set", file=sys.stderr)
        sys.exit(1)
    
    # Determine request type from prompt
    prompt_lower = prompt.lower()
    is_password = 'password' in prompt_lower or 'passphrase' in prompt_lower
    is_confirmation = (
        'confirm' in prompt_lower or 
        'touch' in prompt_lower or
        'presence' in prompt_lower or
        'yubikey' in prompt_lower or
        'security key' in prompt_lower or
        'tap' in prompt_lower
    )
    
    # Connect to server
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(sock_path)
        
        # Send request
        request = {{
            'prompt': prompt,
            'is_password': is_password,
            'is_confirmation': is_confirmation,
        }}
        sock.sendall(json.dumps(request).encode() + b'\\n')
        
        # Read response
        data = b''
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
            if b'\\n' in data:
                break
        
        sock.close()
        
        response = json.loads(data.decode().strip())
        
        if response.get('success'):
            # Print value to stdout (SSH reads this)
            print(response.get('value', ''))
            sys.exit(0)
        else:
            print(response.get('error', 'Authentication cancelled'), file=sys.stderr)
            sys.exit(1)
            
    except Exception as e:
        print(f"Askpass error: {{e}}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
'''
        
        with open(self._helper_path, 'w') as f:
            f.write(script)
        
        # Make executable
        os.chmod(self._helper_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP)
        
        logger.debug(f"Created askpass helper: {self._helper_path}")
    
    def _server_loop(self) -> None:
        """Main server loop - accepts connections and handles requests."""
        while self._running:
            try:
                client, _ = self._server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            
            # Handle client in same thread (requests are sequential)
            try:
                self._handle_client(client)
            except Exception as e:
                logger.exception(f"Error handling askpass client: {e}")
            finally:
                try:
                    client.close()
                except:
                    pass
    
    def _handle_client(self, client: socket.socket) -> None:
        """Handle a single askpass request."""
        # Read request
        data = b''
        client.settimeout(30.0)  # Timeout for reading
        while True:
            chunk = client.recv(4096)
            if not chunk:
                return
            data += chunk
            if b'\n' in data:
                break
        
        # Parse request
        try:
            req_data = json.loads(data.decode().strip())
            request = AskpassRequest(
                prompt=req_data.get('prompt', 'Password: '),
                is_password=req_data.get('is_password', True),
                is_confirmation=req_data.get('is_confirmation', False),
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Invalid askpass request: {e}")
            response = AskpassResponse(success=False, error="Invalid request")
            client.sendall(json.dumps({'success': False, 'error': str(e)}).encode() + b'\n')
            return
        
        logger.info(f"Askpass request: {request.prompt}")
        
        # Call handler
        if self._handler:
            try:
                response = self._handler(request)
            except Exception as e:
                logger.exception(f"Askpass handler error: {e}")
                response = AskpassResponse(success=False, error=str(e))
        else:
            logger.warning("No askpass handler set")
            response = AskpassResponse(success=False, error="No handler")
        
        # Send response
        resp_data = {
            'success': response.success,
            'value': response.value,
            'error': response.error,
        }
        client.sendall(json.dumps(resp_data).encode() + b'\n')


class BlockingAskpassHandler:
    """
    Simple blocking handler that waits for GUI to provide response.
    
    Usage with Qt:
        handler = BlockingAskpassHandler()
        server.set_handler(handler.handle_request)
        
        # In your Qt code, connect to handler.request_received signal
        # and call handler.provide_response() when user responds
    """
    
    def __init__(self):
        self._pending_request: Optional[AskpassRequest] = None
        self._response: Optional[AskpassResponse] = None
        self._event = threading.Event()
        self._lock = threading.Lock()
        
        # Callback for when request is received (call from Qt signal)
        self.on_request: Optional[Callable[[AskpassRequest], None]] = None
    
    def handle_request(self, request: AskpassRequest) -> AskpassResponse:
        """
        Handle an askpass request. Blocks until provide_response() is called.
        Called from askpass server thread.
        """
        with self._lock:
            self._pending_request = request
            self._response = None
            self._event.clear()
        
        # Notify GUI (if callback set)
        if self.on_request:
            try:
                self.on_request(request)
            except Exception as e:
                logger.exception(f"on_request callback error: {e}")
        
        # Wait for response (with timeout)
        if not self._event.wait(timeout=120.0):  # 2 minute timeout
            return AskpassResponse(success=False, error="Timeout waiting for response")
        
        with self._lock:
            response = self._response or AskpassResponse(success=False, error="No response")
            self._pending_request = None
            self._response = None
            return response
    
    def provide_response(self, success: bool, value: str = "", error: str = "") -> None:
        """
        Provide response to pending request. Call from GUI thread.
        """
        with self._lock:
            self._response = AskpassResponse(success=success, value=value, error=error)
        self._event.set()
    
    def cancel(self) -> None:
        """Cancel pending request."""
        self.provide_response(success=False, error="Cancelled by user")
    
    @property
    def has_pending_request(self) -> bool:
        """Check if there's a pending request."""
        with self._lock:
            return self._pending_request is not None
    
    @property
    def pending_prompt(self) -> Optional[str]:
        """Get the pending request prompt, if any."""
        with self._lock:
            return self._pending_request.prompt if self._pending_request else None
