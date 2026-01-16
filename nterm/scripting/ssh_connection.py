"""
nterm/scripting/ssh_connection.py

Low-level SSH connection and command execution utilities.
Incorporates ANSI filtering, sophisticated prompt detection, and legacy device support.
"""

import time
import re
import paramiko
from typing import Optional, List, Tuple
from io import StringIO

from ..connection.profile import ConnectionProfile, AuthMethod


# =============================================================================
# ANSI Filtering
# =============================================================================

def filter_ansi_sequences(text: str) -> str:
    """
    Aggressively filter ANSI escape sequences and control characters.

    Catches: \\x1b[1;24r, \\x1b[24;1H, \\x1b[2K, \\x1b[?25h, etc.

    Args:
        text: Input text with potential ANSI sequences

    Returns:
        Cleaned text
    """
    if not text:
        return text

    # Comprehensive regex for all ANSI sequences and control chars
    ansi_pattern = r'\x1b\[[0-9;?]*[a-zA-Z]|\x1b[()][AB012]|\x07|[\x00-\x08\x0B\x0C\x0E-\x1F]'
    return re.sub(ansi_pattern, '', text)


# =============================================================================
# Legacy Algorithm Support
# =============================================================================

def configure_legacy_algorithms():
    """
    Configure Paramiko for legacy algorithm support.

    Enables older KEX, ciphers, and key types for compatibility with
    legacy network devices (old Cisco IOS, etc.)
    """
    paramiko.Transport._preferred_kex = (
        # Legacy KEX algorithms first
        "diffie-hellman-group1-sha1",
        "diffie-hellman-group14-sha1",
        "diffie-hellman-group-exchange-sha1",
        "diffie-hellman-group-exchange-sha256",
        # Modern algorithms
        "ecdh-sha2-nistp256",
        "ecdh-sha2-nistp384",
        "ecdh-sha2-nistp521",
        "curve25519-sha256",
        "curve25519-sha256@libssh.org",
        "diffie-hellman-group16-sha512",
        "diffie-hellman-group18-sha512"
    )

    paramiko.Transport._preferred_ciphers = (
        # Legacy ciphers first
        "aes128-cbc",
        "aes256-cbc",
        "3des-cbc",
        "aes192-cbc",
        # Modern ciphers
        "aes128-ctr",
        "aes192-ctr",
        "aes256-ctr",
        "aes256-gcm@openssh.com",
        "aes128-gcm@openssh.com",
        "chacha20-poly1305@openssh.com",
    )

    paramiko.Transport._preferred_keys = (
        # Legacy key types first
        "ssh-rsa",
        "ssh-dss",
        # Modern key types
        "ecdsa-sha2-nistp256",
        "ecdsa-sha2-nistp384",
        "ecdsa-sha2-nistp521",
        "ssh-ed25519",
        "rsa-sha2-256",
        "rsa-sha2-512"
    )


# Disabled algorithms for RSA-SHA1 fallback
RSA_SHA1_DISABLED_ALGORITHMS = {
    'pubkeys': ['rsa-sha2-512', 'rsa-sha2-256']
}


# =============================================================================
# Prompt Detection
# =============================================================================

# Common prompt ending characters
PROMPT_CHARS = ['#', '>', '$', '%', ':', ']', ')']

# Prompt detection patterns (ordered by specificity)
PROMPT_PATTERNS = [
    r'([^\r\n]*[#>$%])\s*$',           # Standard prompts
    r'([A-Za-z0-9\-_.]+[#>$%])\s*$',   # Hostname-style prompts
    r'([A-Za-z0-9\-_.@]+[#>$%])\s*$',  # user@host style
    r'(\S+[#>$%])\s*$',                # Any non-whitespace + prompt char
]


def _extract_clean_prompt(buffer: str) -> Optional[str]:
    """
    Extract a clean prompt from buffer, handling repeated prompts.

    Example: 'device# device# device#' -> 'device#'
    """
    if not buffer or not buffer.strip():
        return None

    # Filter ANSI first
    clean_buffer = filter_ansi_sequences(buffer)

    # Get non-empty lines
    lines = [line.strip() for line in clean_buffer.split('\n') if line.strip()]
    if not lines:
        return None

    last_line = lines[-1]

    # Check for simple prompt (no repetition)
    if any(last_line.endswith(char) for char in PROMPT_CHARS) and len(last_line) < 50:
        # Check for repeated pattern
        base_prompt = _extract_base_prompt(last_line)
        if base_prompt:
            return base_prompt
        return last_line

    # Try each line in reverse
    for line in reversed(lines):
        if any(line.endswith(char) for char in PROMPT_CHARS):
            base_prompt = _extract_base_prompt(line)
            if base_prompt:
                return base_prompt
            if len(line) < 50:
                return line

    # Regex fallback
    for pattern in PROMPT_PATTERNS:
        match = re.search(pattern, clean_buffer)
        if match:
            return match.group(1).strip()

    # Last resort
    if lines and len(lines[-1]) < 50:
        return lines[-1]

    return None


def _extract_base_prompt(text: str) -> Optional[str]:
    """
    Extract base prompt from text with possible repetitions.

    Example: 'device# device# device#' -> 'device#'
    """
    # Check each prompt character
    for char in PROMPT_CHARS:
        if char in text:
            parts = text.split(char)
            if len(parts) > 1:
                # Check if all parts before last are identical
                base_parts = [part.strip() for part in parts[:-1]]
                if base_parts and all(part == base_parts[0] for part in base_parts):
                    return base_parts[0] + char

    # Check for whitespace-separated repetitions
    parts = text.split()
    if len(parts) > 1:
        potential_prompts = [
            part for part in parts
            if any(part.endswith(char) for char in PROMPT_CHARS)
        ]
        if len(potential_prompts) > 1 and len(set(potential_prompts)) == 1:
            return potential_prompts[0]

    return None


def _scrub_prompt(raw_prompt: str) -> str:
    """
    Clean up a detected prompt to get just the prompt pattern.

    Handles cases where prompt is mixed with command echo or garbage.
    """
    lines = raw_prompt.strip().split('\n')
    cleaned_lines = [line.strip() for line in lines if line.strip()]

    # Look through lines in reverse for prompt-like patterns
    for line in reversed(cleaned_lines):
        if any(line.endswith(char) for char in PROMPT_CHARS):
            # If line has spaces, try to extract just the prompt part
            if ' ' in line:
                parts = line.split()
                # Check last part
                if parts[-1][-1] in '#>$%':
                    return parts[-1]

                # Try splitting by prompt char
                for char in PROMPT_CHARS:
                    if char in line:
                        prompt_parts = line.split(char)
                        if len(prompt_parts) > 1:
                            potential = prompt_parts[0] + char
                            if len(potential) < 30 and ' ' not in potential[-15:]:
                                return potential
            else:
                return line

    # Regex fallback
    for pattern in PROMPT_PATTERNS:
        match = re.search(pattern, raw_prompt)
        if match:
            return match.group(1)

    # Last resort
    if cleaned_lines and len(cleaned_lines[-1]) < 50:
        return cleaned_lines[-1]

    return raw_prompt


# =============================================================================
# Paging Detection (Error Condition)
# =============================================================================

PAGING_PROMPTS = [
    '--More--',
    '-- More --',
    '<--- More --->',
    'Press any key to continue',
    '--more--',
    ' --More-- ',
]


class PagingNotDisabledError(Exception):
    """
    Raised when paging prompt is detected during command execution.

    This indicates that terminal paging was not properly disabled.
    The caller should ensure 'terminal length 0' (or equivalent) is sent
    before executing commands.
    """
    pass


# =============================================================================
# Core Functions
# =============================================================================

def wait_for_prompt(
    shell: paramiko.Channel,
    timeout: int = 10,
    initial_wait: float = 0.5,
) -> str:
    """
    Wait for device prompt and return detected prompt pattern.

    Args:
        shell: Active SSH channel
        timeout: Maximum wait time in seconds
        initial_wait: Initial sleep before sending newline

    Returns:
        Detected prompt string
    """
    time.sleep(initial_wait)

    # Clear any pending data
    while shell.recv_ready():
        shell.recv(65536)

    # Send newline to trigger prompt
    shell.send('\n')
    time.sleep(0.3)

    output = ""
    end_time = time.time() + timeout

    while time.time() < end_time:
        if shell.recv_ready():
            chunk = shell.recv(4096).decode('utf-8', errors='ignore')
            output += chunk
            time.sleep(0.1)
        else:
            # Give a moment for any trailing data
            time.sleep(0.2)
            if not shell.recv_ready():
                break

    # Filter ANSI and extract prompt
    filtered_output = filter_ansi_sequences(output)
    prompt = _extract_clean_prompt(filtered_output)

    if prompt:
        return _scrub_prompt(prompt)

    # Fallback: last line
    lines = filtered_output.strip().split('\n')
    if lines:
        last_line = lines[-1].strip()
        if last_line and last_line[-1] in PROMPT_CHARS:
            return last_line

    # Default fallback
    return '#'


def send_command(
    shell: paramiko.Channel,
    command: str,
    prompt: str,
    timeout: int = 30,
) -> str:
    """
    Send command and collect output until prompt returns.

    Args:
        shell: Active SSH channel
        command: Command to execute
        prompt: Expected prompt pattern
        timeout: Command timeout in seconds

    Returns:
        Command output (without echoed command and prompt)

    Raises:
        PagingNotDisabledError: If paging prompt detected (terminal length not set)
        TimeoutError: If prompt not seen within timeout
    """
    # Clear any pending input
    time.sleep(0.1)
    while shell.recv_ready():
        shell.recv(65536)
        time.sleep(0.05)

    # Send command
    command = command.strip()
    shell.send(command + '\n')
    time.sleep(0.3)  # Allow device to echo command

    output = ""
    end_time = time.time() + timeout
    prompt_seen = False

    while time.time() < end_time:
        if shell.recv_ready():
            chunk = shell.recv(65536).decode('utf-8', errors='ignore')

            # Filter ANSI immediately
            filtered_chunk = filter_ansi_sequences(chunk)
            output += filtered_chunk

            # Check for paging prompt - this is an ERROR condition
            for paging_prompt in PAGING_PROMPTS:
                if paging_prompt in output:
                    raise PagingNotDisabledError(
                        f"Paging prompt '{paging_prompt}' detected. "
                        f"Terminal paging was not disabled. "
                        f"Ensure 'terminal length 0' (or equivalent) is sent before commands."
                    )

            # Check for final prompt
            if prompt in output:
                prompt_seen = True
                # Give a bit more time for trailing data
                time.sleep(0.1)
                if shell.recv_ready():
                    chunk = shell.recv(65536).decode('utf-8', errors='ignore')
                    output += filter_ansi_sequences(chunk)
                break

            time.sleep(0.05)
        else:
            if prompt_seen:
                break
            time.sleep(0.1)

    if not prompt_seen and prompt not in output:
        # Check one more time
        time.sleep(0.5)
        while shell.recv_ready():
            chunk = shell.recv(65536).decode('utf-8', errors='ignore')
            output += filter_ansi_sequences(chunk)

        if prompt not in output:
            raise TimeoutError(
                f"Prompt '{prompt}' not seen within {timeout}s. "
                f"Command may still be running or prompt detection failed. "
                f"Output tail: ...{output[-200:] if len(output) > 200 else output}"
            )

    # Clean up output
    lines = output.split('\n')

    # Remove first line if it contains the echoed command
    if lines and command.lower() in lines[0].lower():
        lines = lines[1:]

    # Remove last line if it's the prompt
    if lines and prompt in lines[-1]:
        lines = lines[:-1]

    # Filter out empty lines and prompt-only lines
    cleaned_lines = []
    for line in lines:
        stripped = line.rstrip('\r\n')
        # Skip prompt lines
        if stripped.strip() == prompt.strip():
            continue
        cleaned_lines.append(stripped)

    return '\n'.join(cleaned_lines).strip()


def connect_ssh(
    hostname: str,
    port: int,
    profile: ConnectionProfile,
    debug: bool = False,
) -> Tuple[paramiko.SSHClient, paramiko.Channel, str, List[str]]:
    """
    Establish SSH connection and return client, shell, and prompt.

    Args:
        hostname: Target hostname or IP
        port: SSH port
        profile: ConnectionProfile with authentication details
        debug: Enable verbose debugging

    Returns:
        Tuple of (ssh_client, shell_channel, prompt, debug_log)

    Raises:
        paramiko.AuthenticationException: On auth failure
        ConnectionError: On connection failure
    """
    debug_log = []

    def _debug(msg):
        if debug:
            debug_log.append(msg)
            print(f"[DEBUG] {msg}")

    # Configure legacy algorithm support
    configure_legacy_algorithms()

    # Prepare connection kwargs
    connect_kwargs = {
        'hostname': hostname,
        'port': port,
        'timeout': 10,
        'allow_agent': False,
        'look_for_keys': False,
    }

    # Add authentication from profile
    auth_method_used = None

    if profile.auth_methods:
        first_auth = profile.auth_methods[0]
        connect_kwargs['username'] = first_auth.username
        _debug(f"Username: {first_auth.username}")

        for auth in profile.auth_methods:
            if auth.method == AuthMethod.PASSWORD:
                connect_kwargs['password'] = auth.password
                auth_method_used = "password"
                _debug("Auth method: password")
                break

            elif auth.method == AuthMethod.KEY_FILE:
                connect_kwargs['key_filename'] = auth.key_path
                if auth.key_passphrase:
                    connect_kwargs['passphrase'] = auth.key_passphrase
                auth_method_used = f"key_file:{auth.key_path}"
                _debug(f"Auth method: key_file ({auth.key_path})")
                break

            elif auth.method == AuthMethod.KEY_STORED:
                # In-memory key from vault - load via StringIO
                pkey = _load_key_from_content(auth.key_data, auth.key_passphrase)
                if pkey:
                    connect_kwargs['pkey'] = pkey
                    auth_method_used = "key_stored"
                    _debug("Auth method: key_stored (in-memory)")
                    break

    # Detect key type if using key file
    if 'key_filename' in connect_kwargs:
        key_path = connect_kwargs['key_filename']
        key_type, key_bits = _detect_key_type(key_path)
        _debug(f"Key type: {key_type}" + (f" ({key_bits} bits)" if key_bits else ""))

    # Connection attempts: modern first, then legacy fallback
    attempts = [
        ("modern", None),
        ("rsa-sha1", RSA_SHA1_DISABLED_ALGORITHMS),
    ]

    last_error = None
    connected = False
    client = None

    for attempt_name, disabled_algs in attempts:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        _debug(f"Attempt: {attempt_name}")

        attempt_kwargs = connect_kwargs.copy()
        if disabled_algs:
            attempt_kwargs['disabled_algorithms'] = disabled_algs
            _debug(f"  disabled_algorithms: {disabled_algs}")

        try:
            client.connect(**attempt_kwargs)
            connected = True

            # Log negotiated algorithms
            transport = client.get_transport()
            if transport:
                _debug(f"  SUCCESS - cipher: {transport.remote_cipher}, mac: {transport.remote_mac}")
                _debug(f"  host_key_type: {transport.host_key_type}")

                # Set keepalive for long operations
                transport.set_keepalive(30)
            break

        except paramiko.AuthenticationException as e:
            _debug(f"  FAILED (auth): {e}")
            last_error = str(e)
            client.close()
        except paramiko.SSHException as e:
            _debug(f"  FAILED (ssh): {e}")
            last_error = str(e)
            client.close()
        except Exception as e:
            _debug(f"  FAILED (other): {e}")
            last_error = str(e)
            client.close()

    if not connected:
        error_detail = f"Connection failed: {last_error}"
        if debug:
            error_detail += f"\n\nDebug log:\n" + "\n".join(debug_log)
        raise paramiko.AuthenticationException(error_detail)

    # Open interactive shell
    shell = client.invoke_shell(width=200, height=50)
    shell.settimeout(0.5)

    # Wait for shell initialization
    time.sleep(1.0)

    # Clear initial banner/MOTD
    while shell.recv_ready():
        shell.recv(65536)

    # Detect prompt
    prompt = wait_for_prompt(shell)
    _debug(f"Prompt detected: '{prompt}'")

    return client, shell, prompt, debug_log


def _load_key_from_content(key_content: str, passphrase: Optional[str] = None) -> Optional[paramiko.PKey]:
    """
    Load private key from string content (for vault-stored keys).

    Tries Ed25519, RSA, ECDSA in order.
    """
    key_types = [
        ('Ed25519', paramiko.Ed25519Key),
        ('RSA', paramiko.RSAKey),
        ('ECDSA', paramiko.ECDSAKey),
    ]

    # Add DSA if available (older Paramiko)
    if hasattr(paramiko, 'DSSKey'):
        key_types.append(('DSA', paramiko.DSSKey))

    for key_name, key_class in key_types:
        try:
            key_io = StringIO(key_content)
            if passphrase:
                return key_class.from_private_key(key_io, password=passphrase)
            else:
                return key_class.from_private_key(key_io)
        except paramiko.ssh_exception.PasswordRequiredException:
            raise ValueError("Private key requires a password but none provided")
        except (paramiko.ssh_exception.SSHException, Exception):
            continue

    return None


def _detect_key_type(key_path: str) -> Tuple[str, Optional[int]]:
    """Detect SSH key type and bit length."""
    key_types = [
        ('RSA', paramiko.RSAKey),
        ('Ed25519', paramiko.Ed25519Key),
        ('ECDSA', paramiko.ECDSAKey),
    ]

    for key_name, key_class in key_types:
        try:
            key = key_class.from_private_key_file(key_path)
            bits = key.get_bits() if hasattr(key, 'get_bits') else None
            return key_name, bits
        except Exception:
            continue

    return "unknown", None