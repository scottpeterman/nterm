# nterm

**A modern SSH terminal for network engineers**

PyQt6 terminal widget with encrypted credential vault, jump host chaining, YubiKey/FIDO2 support, and legacy device compatibility.

Built for managing hundreds of devices through bastion hosts with hardware security keys.

![nterm screenshot](https://raw.githubusercontent.com/scottpeterman/nterm/main/screenshots/slides.gif)

---

## Features

**Terminal**
- xterm.js rendering via QWebEngineView — full VT100/ANSI support
- Built-in themes: Catppuccin, Dracula, Nord, Solarized, Gruvbox (dark/light/hybrid)
- Custom YAML themes with independent terminal and UI colors
- Tab or window per session — pop sessions to separate windows
- Unicode, emoji, box-drawing characters

**Authentication**
- SSH Agent with YubiKey/FIDO2 hardware keys
- Password, key file, keyboard-interactive, certificate auth
- Multiple auth methods with automatic fallback
- RSA SHA-1 fallback for legacy devices (OpenSSH < 7.2)
- Legacy crypto support for old Juniper/Cisco gear

**Connection Management**  
- Jump host chaining (unlimited hops)
- Auto-reconnection with exponential backoff
- Connection profiles in YAML/JSON
- Pattern-based credential resolution

**Credential Vault**
- AES-256 encryption with PBKDF2 (480,000 iterations)
- Pattern matching — map credentials to hosts by wildcard or tag
- Cross-platform keychain: macOS Keychain, Windows Credential Locker, Linux Secret Service
- Full PyQt6 management UI

**Scripting API** *(Experimental)*
- Query device inventory and credentials programmatically
- Built-in IPython console with API pre-loaded
- CLI for shell scripts and automation
- Foundation for MCP tools and agentic workflows

---

## Screenshots

| Gruvbox Hybrid Theme | Credential Manager |
|---------------------|-------------------|
| ![gruvbox](https://raw.githubusercontent.com/scottpeterman/nterm/main/screenshots/gruvbox.png) | ![vault](https://raw.githubusercontent.com/scottpeterman/nterm/main/screenshots/vault.png) |

| Connection Dialog                                                                            | Multi-vendor Support |
|----------------------------------------------------------------------------------------------|---------------------|
| ![connect](https://raw.githubusercontent.com/scottpeterman/nterm/main/screenshots/creds.png) | ![neofetch](https://raw.githubusercontent.com/scottpeterman/nterm/main/screenshots/neofetch.png) |

---

## Dev Console

nterm includes a built-in development console accessible via **Dev → IPython** or **Dev → Shell**. Open in a tab alongside your SSH sessions, or pop out to a separate window.

![IPython Console](https://raw.githubusercontent.com/scottpeterman/nterm/main/screenshots/ipython.png)

The IPython console runs in the same Python environment as nterm, with the scripting API pre-loaded. Query your device inventory, inspect credentials, and prototype automation workflows without leaving the app.

```python
# Available immediately when IPython opens
api.devices()                    # List all saved devices
api.search("leaf")               # Search by name/hostname  
api.credentials()                # List credentials (after api.unlock())
api.help()                       # Show all commands
```

**Use cases:**
- Debug connection issues with live access to session objects
- Prototype automation scripts against your real device inventory
- Test credential resolution patterns
- Build and test MCP tools interactively

Requires the `scripting` extra: `pip install ntermqt[scripting]`

---

## Installation

### Be aware due to a naming conflict, the pypi package is actually "ntermqt"

### From PyPI

https://pypi.org/project/ntermqt/

```bash
pip install ntermqt

# With optional scripting support (IPython)
pip install ntermqt[scripting]

# With all optional features
pip install ntermqt[all]

# Run
nterm
```

### From Source

```bash
git clone https://github.com/scottpeterman/nterm.git
cd nterm

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install in development mode
pip install -e ".[all]"

# Run
nterm
# or
python -m nterm
```

### Requirements

- Python 3.10+
- PyQt6 with WebEngine
- paramiko
- cryptography
- pyyaml

### Platform Support

| Platform | PTY | Keychain |
|----------|-----|----------|
| Linux | ✅ pexpect | Secret Service |
| macOS | ✅ pexpect | macOS Keychain |
| Windows 10+ | ✅ pywinpty | Credential Locker |

---

## Scripting API *(Experimental)*

nterm includes a scripting API for programmatic access to your device inventory and credential vault. Use it from IPython, CLI, or Python scripts.

### IPython Console

Open **Dev → IPython → Open in Tab** to get an interactive console with the API pre-loaded:

```python
api.devices()                    # List all saved devices
api.search("leaf")               # Search by name/hostname
api.devices("eng-*")             # Glob pattern filter

api.unlock("vault-password")     # Unlock credential vault
api.credentials()                # List credentials (metadata only)

api.help()                       # Show all commands
```

### CLI

```bash
nterm-cli devices                     # List all devices
nterm-cli search leaf                 # Search devices
nterm-cli device eng-leaf-1           # Device details
nterm-cli credentials --unlock        # List credentials
nterm-cli --json devices              # JSON output for scripting
```

### Python Scripts

```python
from nterm.scripting import NTermAPI

api = NTermAPI()

# Query devices
for device in api.devices("*spine*"):
    print(f"{device.name}: {device.hostname}")

# Work with credentials
api.unlock("vault-password")
cred = api.credential("lab-admin")
print(f"Username: {cred.username}")
```

### Roadmap

The scripting API is the foundation for:

- **Command execution** — `api.connect()` and `api.send()` for programmatic device interaction
- **Batch operations** — Fan out commands across device groups
- **MCP tool integration** — Expose nterm capabilities to AI agents

See [scripting/README.md](nterm/scripting/README.md) for full API documentation.

---

## Quick Start

### As a Widget

```python
from PyQt6.QtWidgets import QApplication, QMainWindow
from nterm import ConnectionProfile, AuthConfig, SSHSession, TerminalWidget, Theme

app = QApplication([])

terminal = TerminalWidget()
terminal.set_theme(Theme.gruvbox_hybrid())

profile = ConnectionProfile(
    name="router",
    hostname="192.168.1.1",
    auth_methods=[AuthConfig.password_auth("admin", "secret")],
)

session = SSHSession(profile)
terminal.attach_session(session)
session.connect()

window = QMainWindow()
window.setCentralWidget(terminal)
window.resize(1000, 700)
window.show()

app.exec()
```

### With Credential Vault

```python
from nterm.vault import CredentialStore, CredentialResolver

store = CredentialStore()
store.unlock("master-password")

# Add credential with pattern matching
store.add_credential(
    name="network-devices",
    username="admin",
    password="secret",
    match_hosts=["*.network.corp", "192.168.1.*"],
    match_tags=["cisco", "juniper"],
)

# Auto-resolve credentials by hostname
resolver = CredentialResolver(store)
profile = resolver.resolve_for_device("switch01.network.corp", tags=["cisco"])

session = SSHSession(profile)
session.connect()
```

---

## Themes

### Built-in

```python
Theme.default()         # Catppuccin Mocha
Theme.dracula()         # Dracula
Theme.nord()            # Nord
Theme.solarized_dark()  # Solarized Dark
Theme.gruvbox_dark()    # Gruvbox Dark
Theme.gruvbox_light()   # Gruvbox Light
Theme.gruvbox_hybrid()  # Dark UI + Light terminal
```

### Custom YAML

```yaml
# ~/.nterm/themes/my-theme.yaml
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
  # ... bright variants

# UI chrome (can differ from terminal)
background_color: "#1a1b26"
foreground_color: "#c0caf5"
border_color: "#33467c"
accent_color: "#7aa2f7"
```

---

## Jump Hosts

```python
profile = ConnectionProfile(
    name="internal-db",
    hostname="db01.internal.corp",
    auth_methods=[AuthConfig.agent_auth("dbadmin")],
    jump_hosts=[
        JumpHostConfig(
            hostname="bastion.corp.com",
            auth=AuthConfig.agent_auth("youruser"),
            requires_touch=True,
            touch_prompt="Touch YubiKey for bastion...",
        ),
    ],
)
```

---

## Legacy Device Support

nterm automatically handles old network equipment:

- **RSA SHA-1 fallback** for OpenSSH < 7.2 servers
- **Legacy KEX algorithms**: diffie-hellman-group14-sha1, group1-sha1
- **Legacy ciphers**: aes128-cbc, 3des-cbc
- **Auto-detection**: tries modern crypto first, falls back as needed

Tested with:
- Junos 14.x (2016)
- Cisco IOS 12.2
- Old Arista EOS
- Any device running OpenSSH 6.x

---

## Architecture

```
nterm/
├── connection/        # ConnectionProfile, AuthConfig, JumpHostConfig
├── session/
│   ├── ssh.py         # SSHSession (Paramiko) with legacy fallback
│   ├── interactive_ssh.py   # Native SSH + PTY
│   ├── local_terminal.py    # Local shell/IPython sessions
│   └── pty_transport.py     # Cross-platform PTY
├── terminal/
│   ├── widget.py      # TerminalWidget (PyQt6 + xterm.js)
│   └── bridge.py      # Qt ↔ JavaScript bridge
├── theme/
│   ├── engine.py      # Theme system
│   └── themes/        # YAML theme files
├── vault/
│   ├── store.py       # Encrypted credential storage
│   ├── resolver.py    # Pattern-based resolution
│   └── manager_ui.py  # PyQt6 credential manager
├── manager/           # Session tree, connection dialogs
└── scripting/         # API, CLI, automation support
    ├── api.py         # NTermAPI class
    └── cli.py         # nterm-cli entry point
```

---

## Related Projects

- [TerminalTelemetry](https://github.com/scottpeterman/terminaltelemetry) — PyQt6 terminal with network monitoring
- [Secure Cartography](https://github.com/scottpeterman/secure_cartography) — Network discovery and mapping

---

## License

GPLv3

---

## Contributing

Contributions welcome:
- Additional themes
- Windows testing  
- Session recording/playback
- Telnet/serial support