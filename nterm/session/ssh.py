"""
SSH session implementation using Paramiko.
"""

from __future__ import annotations
import socket
import threading
import time
import logging
import warnings
from typing import Optional, Callable
from io import StringIO

import paramiko

from .base import (
    Session, SessionState, SessionEvent,
    DataReceived, StateChanged, InteractionRequired, BannerReceived
)
from ..connection.profile import (
    ConnectionProfile, AuthMethod, AuthConfig, JumpHostConfig
)

logger = logging.getLogger(__name__)


# =============================================================================
# Legacy Device Support - Algorithm Configuration
# =============================================================================
# These settings provide broad compatibility with older network devices
# (old Juniper, Cisco IOS, etc.) while still preferring modern algorithms.

PREFERRED_CIPHERS = (
    "aes128-ctr",
    "aes192-ctr",
    "aes256-ctr",
    "aes128-gcm@openssh.com",
    "aes256-gcm@openssh.com",
    "chacha20-poly1305@openssh.com",
    "aes128-cbc",
    "aes192-cbc",
    "aes256-cbc",
    "3des-cbc",
)

PREFERRED_KEX = (
    "curve25519-sha256",
    "curve25519-sha256@libssh.org",
    "ecdh-sha2-nistp256",
    "ecdh-sha2-nistp384",
    "ecdh-sha2-nistp521",
    "diffie-hellman-group14-sha256",
    "diffie-hellman-group16-sha512",
    "diffie-hellman-group-exchange-sha256",
    "diffie-hellman-group14-sha1",
    "diffie-hellman-group-exchange-sha1",
    "diffie-hellman-group1-sha1",
)

PREFERRED_KEYS = (
    "rsa-sha2-512",
    "rsa-sha2-256",
    "ssh-rsa",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
    "ssh-ed25519",
)

# Disabled algorithms to force RSA SHA-1 signatures
# Required for old OpenSSH servers (< 7.2) that don't support rsa-sha2-*
RSA_SHA1_DISABLED_ALGORITHMS = {
    'pubkeys': ['rsa-sha2-256', 'rsa-sha2-512']
}

# Flag to track if we've applied global transport settings
_transport_configured = False


def _apply_global_transport_settings() -> None:
    """
    Apply custom transport settings globally to Paramiko for legacy device support.

    This must be called before creating any SSH connections. It modifies the
    Paramiko Transport class to prefer algorithms compatible with older devices.
    """
    global _transport_configured

    if _transport_configured:
        return

    # Suppress deprecation warnings for legacy algorithms
    warnings.filterwarnings('ignore', category=DeprecationWarning, module='paramiko')

    try:
        # Get what Paramiko actually supports
        available_ciphers = set(paramiko.Transport._cipher_info.keys())
        available_kex = set(paramiko.Transport._kex_info.keys())
        available_keys = set(paramiko.Transport._key_info.keys())

        # Filter to only supported algorithms
        ciphers = tuple(c for c in PREFERRED_CIPHERS if c in available_ciphers)
        kex = tuple(k for k in PREFERRED_KEX if k in available_kex)
        keys = tuple(k for k in PREFERRED_KEYS if k in available_keys)

        # Apply globally to Transport class
        paramiko.Transport._preferred_ciphers = ciphers
        paramiko.Transport._preferred_kex = kex
        paramiko.Transport._preferred_keys = keys

        logger.info(
            f"Applied global transport settings: "
            f"{len(ciphers)} ciphers, {len(kex)} kex, {len(keys)} keys"
        )
        logger.debug(f"Ciphers: {ciphers}")
        logger.debug(f"KEX: {kex}")
        logger.debug(f"Keys: {keys}")

    except Exception as e:
        logger.warning(f"Could not apply global transport settings: {e}")

    _transport_configured = True


class SSHSession(Session):
    """
    SSH session with full reconnection support.

    Thread-safe. Runs I/O on background thread,
    emits events to be handled on main thread.

    Supports automatic fallback for:
    - RSA SHA-1 signatures (old OpenSSH < 7.2)
    - Legacy crypto algorithms (old network devices)
    """

    READ_BUFFER_SIZE = 65536

    def __init__(self, profile: ConnectionProfile, vault=None):
        """
        Initialize SSH session.

        Args:
            profile: Connection profile with auth and host info
            vault: Optional credential vault for resolving credential_ref
        """
        # Apply global transport settings on first session creation
        _apply_global_transport_settings()

        self.profile = profile
        self.vault = vault

        self._state = SessionState.DISCONNECTED
        self._state_lock = threading.Lock()

        self._client: Optional[paramiko.SSHClient] = None
        self._channel: Optional[paramiko.Channel] = None
        self._jump_clients: list[paramiko.SSHClient] = []

        self._event_handler: Optional[Callable[[SessionEvent], None]] = None
        self._read_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._reconnect_attempt = 0
        self._cols = profile.term_cols
        self._rows = profile.term_rows

        # Track if we needed RSA SHA-1 fallback (for reconnects)
        self._use_rsa_sha1 = getattr(profile, 'rsa_sha1', False)

    @property
    def state(self) -> SessionState:
        """Current session state (thread-safe)."""
        with self._state_lock:
            return self._state

    @property
    def is_connected(self) -> bool:
        """Is session currently connected and usable?"""
        return self.state == SessionState.CONNECTED

    def set_event_handler(self, handler: Callable[[SessionEvent], None]) -> None:
        """Set callback for session events."""
        self._event_handler = handler

    def set_auto_reconnect(self, enabled: bool) -> None:
        """Enable/disable automatic reconnection."""
        self.profile.auto_reconnect = enabled

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
        """Start connection in background thread."""
        if self.state not in (SessionState.DISCONNECTED, SessionState.FAILED):
            logger.warning(f"Cannot connect from state {self.state}")
            return

        self._stop_event.clear()
        thread = threading.Thread(target=self._connect_thread, daemon=True)
        thread.start()

    def _create_client(self) -> paramiko.SSHClient:
        """Create a new SSHClient with standard settings."""
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        return client

    def _connect_thread(self) -> None:
        """Connection logic - runs on background thread."""
        try:
            self._set_state(SessionState.CONNECTING)

            # Build jump chain if needed
            sock = None
            if self.profile.jump_hosts:
                sock = self._establish_jump_chain()

            # Connect to target
            self._set_state(SessionState.AUTHENTICATING)

            connected = False
            last_error = None

            for auth in self.profile.auth_methods:
                try:
                    logger.info(f"Trying auth method: {auth.method.value}")

                    # Handle agent auth with potential touch prompt
                    if auth.method == AuthMethod.AGENT:
                        self._emit(InteractionRequired(
                            prompt="Authenticate with your security key...",
                            interaction_type="touch"
                        ))

                    self._attempt_connection(auth, sock)
                    connected = True
                    break

                except paramiko.AuthenticationException as e:
                    last_error = e
                    logger.debug(f"Auth method {auth.method} failed: {e}")
                    continue

                except Exception as e:
                    last_error = e
                    logger.debug(f"Connection error with {auth.method}: {e}")
                    continue

            if not connected:
                raise paramiko.AuthenticationException(
                    f"All auth methods failed. Last error: {last_error}"
                )

            # Open shell channel
            self._channel = self._client.invoke_shell(
                term=self.profile.term_type,
                width=self._cols,
                height=self._rows,
            )
            self._channel.settimeout(0.1)

            # Set up keepalive
            transport = self._client.get_transport()
            if transport:
                transport.set_keepalive(self.profile.keepalive_interval)
                logger.debug(
                    f"Negotiated: cipher={transport.remote_cipher}, "
                    f"mac={transport.remote_mac}"
                )

            self._set_state(SessionState.CONNECTED)
            self._reconnect_attempt = 0

            # Start read loop
            self._read_loop()

        except Exception as e:
            logger.exception("Connection failed")
            self._cleanup()
            self._set_state(SessionState.FAILED, str(e))

            # Auto-reconnect if enabled
            if self.profile.auto_reconnect and not self._stop_event.is_set():
                self._schedule_reconnect()

    def _attempt_connection(self, auth: AuthConfig, sock=None) -> None:
        """
        Attempt connection with automatic RSA SHA-1 fallback.

        For RSA keys on old servers (OpenSSH < 7.2), the server may not
        support rsa-sha2-256/512 signatures. We detect this and retry
        with disabled_algorithms to force legacy ssh-rsa (SHA-1).
        """
        kwargs = self._auth_config_to_kwargs(auth)
        if sock:
            kwargs['sock'] = sock

        # If we already know this host needs RSA SHA-1, use it from the start
        if self._use_rsa_sha1:
            kwargs['disabled_algorithms'] = RSA_SHA1_DISABLED_ALGORITHMS
            logger.debug("Using RSA SHA-1 mode (from previous connection)")

        # Determine if this is RSA key auth (for fallback logic)
        is_rsa_key = False
        pkey = kwargs.get('pkey')
        if pkey and isinstance(pkey, paramiko.RSAKey):
            is_rsa_key = True
        elif auth.method == AuthMethod.KEY_FILE and auth.key_path:
            # Check if it's an RSA key file
            try:
                paramiko.RSAKey.from_private_key_file(auth.key_path)
                is_rsa_key = True
            except:
                pass

        # First attempt
        try:
            self._client = self._create_client()
            self._client.connect(
                self.profile.hostname,
                port=self.profile.port,
                timeout=self.profile.connect_timeout,
                **kwargs
            )
            return  # Success!

        except paramiko.AuthenticationException as e:
            # Check if this might be an RSA SHA-2 failure
            if is_rsa_key and not self._use_rsa_sha1:
                logger.info(f"RSA auth failed, retrying with SHA-1 fallback: {e}")

                # Retry with RSA SHA-1
                self._use_rsa_sha1 = True
                kwargs['disabled_algorithms'] = RSA_SHA1_DISABLED_ALGORITHMS

                self._client = self._create_client()
                self._client.connect(
                    self.profile.hostname,
                    port=self.profile.port,
                    timeout=self.profile.connect_timeout,
                    **kwargs
                )
                logger.info("Connected with RSA SHA-1 fallback")
                return

            # Not RSA or already tried SHA-1, re-raise
            raise

    def _establish_jump_chain(self) -> paramiko.Channel:
        """Connect through jump host chain, return channel to final hop."""
        current_sock = None

        for i, jump in enumerate(self.profile.jump_hosts):
            logger.info(
                f"Connecting to jump host {i+1}/{len(self.profile.jump_hosts)}: "
                f"{jump.hostname}"
            )

            if jump.requires_touch:
                self._emit(InteractionRequired(
                    prompt=jump.touch_prompt,
                    interaction_type="touch"
                ))

            jump_client = self._create_client()
            kwargs = self._auth_config_to_kwargs(jump.auth)

            if current_sock:
                kwargs['sock'] = current_sock

            # Check for jump-specific RSA SHA-1 flag
            if getattr(jump, 'rsa_sha1', False):
                kwargs['disabled_algorithms'] = RSA_SHA1_DISABLED_ALGORITHMS

            # Try connection with RSA SHA-1 fallback
            try:
                jump_client.connect(
                    jump.hostname,
                    port=jump.port,
                    timeout=self.profile.connect_timeout,
                    banner_timeout=jump.banner_timeout,
                    **kwargs
                )
            except paramiko.AuthenticationException as e:
                # Try RSA SHA-1 fallback for jump host
                if 'disabled_algorithms' not in kwargs:
                    logger.info(f"Jump host {jump.hostname} auth failed, trying RSA SHA-1")
                    kwargs['disabled_algorithms'] = RSA_SHA1_DISABLED_ALGORITHMS
                    jump_client = self._create_client()
                    jump_client.connect(
                        jump.hostname,
                        port=jump.port,
                        timeout=self.profile.connect_timeout,
                        banner_timeout=jump.banner_timeout,
                        **kwargs
                    )
                else:
                    raise

            self._jump_clients.append(jump_client)

            # Determine next hop
            if i < len(self.profile.jump_hosts) - 1:
                next_hop = self.profile.jump_hosts[i + 1]
                next_host, next_port = next_hop.hostname, next_hop.port
            else:
                next_host = self.profile.hostname
                next_port = self.profile.port

            # Open channel to next hop
            transport = jump_client.get_transport()
            current_sock = transport.open_channel(
                'direct-tcpip',
                dest_addr=(next_host, next_port),
                src_addr=('127.0.0.1', 0)
            )
            logger.debug(f"Opened channel to {next_host}:{next_port}")

        return current_sock

    def _auth_config_to_kwargs(self, auth: AuthConfig) -> dict:
        """Convert AuthConfig to paramiko connect kwargs."""
        if auth is None:
            return {}

        kwargs = {'username': auth.username}

        # Resolve credential reference if needed
        password = auth.password
        key_data = auth.key_data
        key_passphrase = auth.key_passphrase

        if auth.credential_ref and self.vault:
            cred = self.vault.get_credential(auth.credential_ref)
            if cred:
                password = password or cred.password
                key_data = key_data or getattr(cred, 'ssh_key', None)
                key_passphrase = key_passphrase or getattr(cred, 'ssh_key_passphrase', None)

        if auth.method == AuthMethod.PASSWORD:
            kwargs['password'] = password
            kwargs['look_for_keys'] = False
            kwargs['allow_agent'] = False

        elif auth.method == AuthMethod.AGENT:
            kwargs['allow_agent'] = True
            kwargs['look_for_keys'] = False

        elif auth.method == AuthMethod.KEY_FILE:
            kwargs['key_filename'] = auth.key_path
            if key_passphrase:
                kwargs['passphrase'] = key_passphrase
            kwargs['allow_agent'] = auth.allow_agent_fallback
            kwargs['look_for_keys'] = False

        elif auth.method == AuthMethod.KEY_STORED:
            if key_data:
                kwargs['pkey'] = self._load_key_from_string(
                    key_data,
                    key_passphrase
                )
            kwargs['allow_agent'] = auth.allow_agent_fallback
            kwargs['look_for_keys'] = False

        elif auth.method == AuthMethod.CERTIFICATE:
            kwargs['key_filename'] = auth.key_path
            kwargs['allow_agent'] = False
            kwargs['look_for_keys'] = False

        return kwargs

    def _load_key_from_string(
        self,
        key_data: str,
        passphrase: str = None
    ) -> paramiko.PKey:
        """Load SSH key from string data."""
        key_file = StringIO(key_data)

        key_classes = [
            paramiko.RSAKey,
            paramiko.Ed25519Key,
            paramiko.ECDSAKey,
        ]

        for key_class in key_classes:
            try:
                key_file.seek(0)
                return key_class.from_private_key(key_file, password=passphrase)
            except (paramiko.SSHException, ValueError):
                continue

        raise paramiko.SSHException("Unable to parse private key")

    def _read_loop(self) -> None:
        """Read data from channel until stopped or disconnected."""
        while not self._stop_event.is_set():
            try:
                if self._channel and self._channel.recv_ready():
                    data = self._channel.recv(self.READ_BUFFER_SIZE)
                    if data:
                        self._emit(DataReceived(data))
                    else:
                        logger.info("Channel closed by remote")
                        break
                elif self._channel and self._channel.closed:
                    logger.info("Channel closed")
                    break
                else:
                    time.sleep(0.01)

            except socket.timeout:
                continue
            except Exception as e:
                logger.exception("Read error")
                break

        if not self._stop_event.is_set():
            self._cleanup()
            self._set_state(SessionState.DISCONNECTED, "Connection lost")

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
        """Send data to remote."""
        if self._channel and not self._channel.closed:
            try:
                self._channel.sendall(data)
            except Exception as e:
                logger.error(f"Write error: {e}")

    def resize(self, cols: int, rows: int) -> None:
        """Notify remote of terminal resize."""
        self._cols = cols
        self._rows = rows
        if self._channel and not self._channel.closed:
            try:
                self._channel.resize_pty(width=cols, height=rows)
            except Exception as e:
                logger.error(f"Resize error: {e}")

    def disconnect(self) -> None:
        """Gracefully disconnect."""
        logger.info("Disconnecting...")
        self._stop_event.set()
        self._cleanup()
        self._set_state(SessionState.DISCONNECTED, "User disconnected")

    def _cleanup(self) -> None:
        """Clean up connections."""
        if self._channel:
            try:
                self._channel.close()
            except Exception:
                pass
            self._channel = None

        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

        for client in self._jump_clients:
            try:
                client.close()
            except Exception:
                pass
        self._jump_clients.clear()