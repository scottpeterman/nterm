# nterm

A modern, themeable SSH terminal widget for PyQt6 with enterprise features: encrypted credential vault with GUI manager, jump host chaining, YubiKey/FIDO2 support, cross-platform keychain integration, and auto-reconnection.

Built for network engineers who need to manage hundreds of devices through bastion hosts with hardware security keys.

## Features

### Terminal Widget
- **xterm.js rendering** via QWebEngineView for full VT100/ANSI compatibility
- **Themeable UI** with built-in themes (Catppuccin, Dracula, Nord, Solarized) and custom YAML themes
- **Responsive resize** with proper SIGWINCH handling
- **Unicode support** including box-drawing characters and emoji
- **Clickable URLs** with WebLinks addon
- **Session state overlay** showing connection status, reconnection progress

### Authentication
- **SSH Agent** with YubiKey/FIDO2 hardware key support
- **Password authentication** with secure credential storage
- **Key file authentication** with optional passphrase
- **Keyboard-interactive** for MFA/2FA prompts
- **Certificate-based** authentication
- **Multiple auth methods** tried in sequence with automatic fallback

### Connection Management
- **Jump host chaining** via ProxyJump (unlimited hops)
- **Auto-reconnection** with configurable exponential backoff
- **Connection profiles** fully serializable to YAML/JSON
- **Pattern-based credential resolution** for bulk device management

### Credential Vault
- **AES-256 encryption** (Fernet) with PBKDF2 key derivation (480,000 iterations)
- **SQLite storage** with encrypted credential blobs
- **Pattern matching** - map credentials to hosts by wildcard or tag
- **Cross-platform keychain integration** - macOS Keychain, Windows Credential Locker, Linux Secret Service
- **PyQt6 Credential Manager UI** - full CRUD interface with theme support
- **Secure memory handling** - credentials decrypted only when needed

## Installation

```bash
# Clone or extract
cd nterm

# Install dependencies
pip install -r requirements.txt

# Optional: Install keyring for system keychain support
pip install keyring

# Install in development mode
pip install -e .
```

### Requirements

- Python 3.10+
- PyQt6 with WebEngine
- OpenSSH client (for native SSH sessions)
- cryptography (for vault encryption)
- keyring (optional, for system keychain integration)

### Platform Notes

| Platform | PTY Support | Keychain Backend |
|----------|-------------|------------------|
| Linux | ✅ Native | Secret Service (GNOME Keyring / KWallet) |
| macOS | ✅ Native | macOS Keychain |
| Windows 10+ | ✅ pywinpty | Windows Credential Locker |

## Quick Start

```python
from PyQt6.QtWidgets import QApplication, QMainWindow
from nterm import (
    ConnectionProfile, AuthConfig, SSHSession, 
    TerminalWidget, Theme
)

app = QApplication([])

# Create terminal widget
terminal = TerminalWidget()
terminal.set_theme(Theme.default())  # Catppuccin Mocha

# Define connection
profile = ConnectionProfile(
    name="my-server",
    hostname="server.example.com",
    auth_methods=[AuthConfig.agent_auth("myuser")],
)

# Connect
session = SSHSession(profile)
terminal.attach_session(session)
session.connect()

# Show window
window = QMainWindow()
window.setCentralWidget(terminal)
window.resize(1000, 700)
window.show()

app.exec()
```

## Credential Vault

The vault provides encrypted storage for credentials with pattern-based resolution and a full PyQt6 management interface.

### Credential Manager UI

Launch the standalone credential manager:

```bash
python -m nterm.vault.manager_ui
```

Or embed in your application:

```python
from PyQt6.QtWidgets import QApplication, QMainWindow
from nterm.vault import CredentialManagerWidget
from nterm.theme import Theme

app = QApplication([])

# Create manager with theme
manager = CredentialManagerWidget()
manager.set_theme(Theme.dracula())

# Try auto-unlock from system keychain
if not manager.try_auto_unlock():
    # Will prompt for password
    pass

window = QMainWindow()
window.setCentralWidget(manager)
window.show()
app.exec()
```

The credential manager provides:
- **Vault initialization** with master password
- **Add/Edit/Delete credentials** with full field support
- **SSH key import** from file browser
- **Jump host configuration** including YubiKey touch settings
- **Pattern matching rules** for automatic credential resolution
- **Theme integration** with your terminal theme
- **System keychain** option to remember master password

### Keychain Integration

The vault can optionally store the master password in your system's native keychain:

```python
from nterm.vault import KeychainIntegration, CredentialStore

# Check if keychain is available
if KeychainIntegration.is_available():
    print(f"Using: {KeychainIntegration.get_backend_name()}")
    # e.g., "SecretService" on Linux, "Keychain" on macOS

# Store master password in keychain
store = CredentialStore()
if store.unlock("my-master-password"):
    KeychainIntegration.store_master_password("my-master-password")

# Later: auto-unlock from keychain
password = KeychainIntegration.get_master_password()
if password:
    store.unlock(password)

# Clear from keychain when needed
KeychainIntegration.clear_master_password()
```

### Programmatic Vault Usage

```python
from nterm.vault import CredentialStore, CredentialResolver

# Initialize vault (first time only)
store = CredentialStore()  # Default: ~/.nterm/vault.db
store.init_vault("your-master-password")

# Unlock vault
store.unlock("your-master-password")

# Add credentials
store.add_credential(
    name="network-devices",
    username="admin",
    password="secret123",
    match_hosts=["*.network.corp", "192.168.1.*", "switch*"],
    match_tags=["cisco", "arista", "juniper"],
)

# Add credential with jump host
store.add_credential(
    name="internal-servers",
    username="sysadmin",
    ssh_key=open("~/.ssh/id_ed25519").read(),
    ssh_key_passphrase="keypass",
    jump_host="bastion.corp.com",
    jump_username="youruser",
    jump_auth_method="agent",
    jump_requires_touch=True,
    match_hosts=["*.internal.corp"],
)

# List credentials (metadata only, secrets not decrypted)
for cred in store.list_credentials():
    print(f"{cred.name}: {cred.username} (has_password={cred.has_password})")

# Get credential with decrypted secrets
cred = store.get_credential("network-devices")
print(cred.password)  # Decrypted

# Update credential
store.update_credential("network-devices", password="new-secret")

# Change master password (re-encrypts all credentials)
store.change_master_password("old-password", "new-password")

# Lock when done
store.lock()
```

### Credential Resolution

Automatically match credentials to devices:

```python
from nterm.vault import CredentialResolver

resolver = CredentialResolver()
resolver.unlock_vault("master-password")

# Auto-resolve based on hostname and tags
profile = resolver.resolve_for_device(
    "switch01.network.corp",
    tags=["cisco"]
)

# Profile is ready to use with SSHSession
session = SSHSession(profile)
session.connect()

# Or resolve without raising exception
profile = resolver.resolve_or_default("unknown-host.corp")
if profile is None:
    print("No matching credential found")
```

### Pattern Matching

Credentials are matched using:

1. **Hostname patterns** - Unix-style globs
   - `*.network.corp` - any subdomain
   - `192.168.1.*` - IP prefix
   - `switch[0-9][0-9]` - character classes

2. **Tags** - categorical matching
   - `["cisco", "ios-xe"]`
   - `["datacenter", "production"]`

3. **Specificity scoring** - more specific patterns win
   - Exact match: highest priority
   - Longer patterns: higher priority
   - More matching tags: higher priority
   - Default credential: lowest priority fallback

### Vault Security

| Feature | Implementation |
|---------|---------------|
| Encryption | AES-128-CBC + HMAC-SHA256 (Fernet) |
| Key Derivation | PBKDF2-HMAC-SHA256, 480,000 iterations |
| Storage | SQLite with encrypted credential blobs |
| Verification | Encrypted token verified on unlock |
| Memory | Credentials decrypted on-demand only |
| Keychain | Optional system keychain for master password |

## Session Types

nterm provides multiple session implementations for different use cases:

### SSHSession (Paramiko)

Best for: Automation, stored credentials, programmatic control

```python
from nterm import SSHSession, ConnectionProfile, AuthConfig

profile = ConnectionProfile(
    name="automated-device",
    hostname="switch01.network.corp",
    auth_methods=[
        AuthConfig.password_auth("admin", "secret"),
        AuthConfig.agent_auth("admin"),  # Fallback
    ],
)

session = SSHSession(profile)
```

### AskpassSSHSession (Native SSH + SSH_ASKPASS)

Best for: GUI applications needing password/MFA prompts in dialogs

```python
from nterm.session import AskpassSSHSession

session = AskpassSSHSession(profile)
terminal.attach_session(session)

# Handle authentication prompts
terminal.interaction_required.connect(handle_auth_prompt)
session.connect()
```

### InteractiveSSHSession (Native SSH + PTY)

Best for: Full interactive experience, console-launched applications

```python
from nterm import InteractiveSSHSession

session = InteractiveSSHSession(profile)
```

## Jump Host Configuration

Chain through multiple bastion hosts:

```python
from nterm import ConnectionProfile, AuthConfig, JumpHostConfig

profile = ConnectionProfile(
    name="internal-server",
    hostname="db01.internal.corp",
    port=22,
    auth_methods=[AuthConfig.agent_auth("dbadmin")],
    jump_hosts=[
        JumpHostConfig(
            hostname="bastion.corp.com",
            auth=AuthConfig.agent_auth("youruser"),
            requires_touch=True,
            touch_prompt="Touch YubiKey for bastion...",
        ),
        JumpHostConfig(
            hostname="jump.internal.corp",
            port=2222,
            auth=AuthConfig.agent_auth("youruser"),
        ),
    ],
)
```

## Themes

### Built-in Themes

```python
from nterm import Theme

terminal.set_theme(Theme.default())        # Catppuccin Mocha
terminal.set_theme(Theme.dracula())        # Dracula
terminal.set_theme(Theme.nord())           # Nord
terminal.set_theme(Theme.solarized_dark()) # Solarized Dark
```

### Custom Themes

Create YAML theme files in `~/.nterm/themes/`:

```yaml
name: my-theme
terminal_colors:
  background: "#1a1b26"
  foreground: "#c0caf5"
  cursor: "#c0caf5"
  black: "#15161e"
  red: "#f7768e"
  green: "#9ece6a"
  yellow: "#e0af68"
  blue: "#7aa2f7"
  magenta: "#bb9af7"
  cyan: "#7dcfff"
  white: "#a9b1d6"
  # ... brightBlack through brightWhite

font_family: "JetBrains Mono, Consolas, monospace"
font_size: 14

background_color: "#1a1b26"
foreground_color: "#c0caf5"
border_color: "#33467c"
accent_color: "#7aa2f7"
```

Load custom themes:

```python
from nterm import ThemeEngine
from pathlib import Path

engine = ThemeEngine(theme_dir=Path("~/.nterm/themes").expanduser())
engine.load_themes()

terminal.set_theme(engine.get_theme("my-theme"))
```

### Theme Integration with Credential Manager

The credential manager UI automatically adapts to your terminal theme:

```python
from nterm.vault import CredentialManagerWidget, ManagerTheme
from nterm.theme import Theme

# Use terminal theme
manager = CredentialManagerWidget()
manager.set_theme(Theme.nord())

# Or create custom manager theme
custom_theme = ManagerTheme(
    background_color="#2e3440",
    foreground_color="#d8dee9",
    accent_color="#88c0d0",
    error_color="#bf616a",
    success_color="#a3be8c",
)
manager.setStyleSheet(custom_theme.to_stylesheet())
```

## Architecture

```
nterm/
├── connection/
│   └── profile.py          # ConnectionProfile, AuthConfig, JumpHostConfig
│
├── session/
│   ├── base.py             # Abstract Session, SessionState, events
│   ├── ssh.py              # SSHSession (Paramiko-based)
│   ├── interactive_ssh.py  # InteractiveSSHSession (native SSH + PTY)
│   ├── askpass_ssh.py      # AskpassSSHSession (native SSH + SSH_ASKPASS)
│   └── pty_transport.py    # Cross-platform PTY abstraction
│
├── terminal/
│   ├── widget.py           # TerminalWidget (PyQt6 + QWebEngineView)
│   ├── bridge.py           # Qt ↔ JavaScript bridge via QWebChannel
│   └── resources/
│       ├── terminal.html   # xterm.js container
│       └── terminal.js     # Terminal initialization
│
├── theme/
│   ├── engine.py           # Theme, ThemeEngine classes
│   └── themes/             # Built-in YAML themes
│
├── vault/
│   ├── store.py            # CredentialStore (encrypted SQLite)
│   ├── resolver.py         # CredentialResolver (pattern matching)
│   ├── keychain.py         # Cross-platform keychain integration
│   └── manager_ui.py       # PyQt6 credential manager GUI
│
├── askpass/
│   └── server.py           # SSH_ASKPASS server for GUI prompts
│
└── examples/
    ├── basic_terminal.py   # Terminal demo
    └── credential_manager.py # Vault manager demo
```

## API Reference

### CredentialStore

```python
class CredentialStore:
    def __init__(self, db_path: Path = None)  # Default: ~/.nterm/vault.db
    
    # Lifecycle
    def is_initialized(self) -> bool
    def init_vault(self, master_password: str) -> None
    def unlock(self, master_password: str) -> bool
    def lock(self) -> None
    def is_unlocked(self) -> bool
    
    # CRUD
    def add_credential(self, name, username, password=None, ssh_key=None, ...) -> int
    def get_credential(self, name: str) -> Optional[StoredCredential]
    def update_credential(self, name: str, **kwargs) -> bool
    def remove_credential(self, name: str) -> bool
    def list_credentials(self) -> list[StoredCredential]
    
    # Utilities
    def set_default(self, name: str) -> bool
    def get_default(self) -> Optional[StoredCredential]
    def change_master_password(self, old: str, new: str) -> bool
```

### CredentialResolver

```python
class CredentialResolver:
    def __init__(self, store: CredentialStore = None)
    
    def resolve_for_device(self, hostname: str, tags: list = None, port: int = 22) -> ConnectionProfile
    def resolve_or_default(self, hostname: str, tags: list = None, port: int = 22) -> Optional[ConnectionProfile]
    def create_profile_for_credential(self, credential_name: str, hostname: str, port: int = 22) -> ConnectionProfile
```

### KeychainIntegration

```python
class KeychainIntegration:
    @classmethod
    def is_available(cls) -> bool
    @classmethod
    def get_backend_name(cls) -> Optional[str]
    @classmethod
    def store_master_password(cls, password: str) -> bool
    @classmethod
    def get_master_password(cls) -> Optional[str]
    @classmethod
    def clear_master_password(cls) -> bool
    @classmethod
    def has_stored_password(cls) -> bool
```

### CredentialManagerWidget

```python
class CredentialManagerWidget(QWidget):
    # Signals
    credential_selected: pyqtSignal(str)  # credential name
    vault_locked: pyqtSignal()
    vault_unlocked: pyqtSignal()
    
    # Methods
    def set_theme(self, theme: Theme) -> None
    def try_auto_unlock(self) -> bool
    def get_selected_credential(self) -> Optional[str]
```

## License

GPLv3 - See license file
## Contributing

Contributions welcome! Areas of interest:
- Additional themes
- Windows testing
- GUI agent integration for YubiKey
- Session recording/playback
- Multi-session tabbed interface