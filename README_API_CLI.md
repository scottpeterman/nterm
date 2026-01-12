# nterm Scripting API

Programmatic access to nterm's device inventory and credential vault.

Use from IPython, CLI, scripts, or as the foundation for MCP tools and agentic workflows.

---

## Quick Start

### IPython (inside nterm)

Open **Dev → IPython → Open in Tab** and the API is pre-loaded:

```python
api.devices()                    # List all saved devices
api.search("leaf")               # Search by name/hostname
api.devices("eng-*")             # Glob pattern filter
api.device("eng-leaf-1")         # Get specific device

api.unlock("vault-password")     # Unlock credential vault
api.credentials()                # List credentials (no secrets exposed)
api.credential("lab-admin")      # Get specific credential info

api.help()                       # Show all commands
```

### CLI

```bash
nterm-cli devices                     # List all devices
nterm-cli search leaf                 # Search devices
nterm-cli device eng-leaf-1           # Device details
nterm-cli credentials --unlock        # List creds (prompts for password)
nterm-cli status                      # Summary

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
print(f"Username: {cred.username}, Has Key: {cred.has_key}")
```

---

## Installation

The scripting module is included with nterm. For CLI support, ensure `click` is installed:

```bash
pip install click>=8.0
```

Add the CLI entry point to your `pyproject.toml`:

```toml
[project.scripts]
nterm = "nterm.__main__:main"
nterm-cli = "nterm.scripting.cli:main"
```

---

## API Reference

### Device Operations

| Method | Description |
|--------|-------------|
| `api.devices(pattern=None, folder=None)` | List devices, optionally filtered by glob pattern or folder |
| `api.search(query)` | Search devices by name, hostname, or description |
| `api.device(name)` | Get specific device by exact name |
| `api.folders()` | List all folder names |

**DeviceInfo fields:**
- `name` - Session/device name
- `hostname` - IP or hostname
- `port` - SSH port
- `folder` - Folder name (or None for root)
- `credential` - Associated credential name
- `last_connected` - Last connection timestamp
- `connect_count` - Total connections

### Credential Operations

All credential operations require an unlocked vault.

| Method | Description |
|--------|-------------|
| `api.unlock(password)` | Unlock the credential vault |
| `api.lock()` | Lock the vault |
| `api.credentials(pattern=None)` | List credentials (metadata only, no secrets) |
| `api.credential(name)` | Get specific credential info |
| `api.resolve_credential(hostname, tags=None)` | Find which credential would match a host |

**Properties:**
- `api.vault_initialized` - Whether vault exists
- `api.vault_unlocked` - Whether vault is currently unlocked

**CredentialInfo fields:**
- `name` - Credential name
- `username` - Username
- `has_password` - Boolean
- `has_key` - Boolean (SSH key stored)
- `match_hosts` - List of host patterns
- `match_tags` - List of tags
- `jump_host` - Jump host if configured
- `is_default` - Whether this is the default credential

### Status

| Method | Description |
|--------|-------------|
| `api.status()` | Returns dict with device count, folder count, credential count, vault status |
| `api.help()` | Print command reference |

---

## CLI Reference

```
Usage: nterm-cli [OPTIONS] COMMAND [ARGS]...

Options:
  --json    Output as JSON
  --help    Show help

Commands:
  devices      List saved devices/sessions
  search       Search devices by name, hostname, or description
  device       Get details for a specific device
  folders      List all folders
  credentials  List credentials (requires unlocked vault)
  credential   Get details for a specific credential
  resolve      Find which credential would be used for a hostname
  status       Show API status summary
```

### Examples

```bash
# Device queries
nterm-cli devices                          # All devices
nterm-cli devices -p "eng-*"               # Filter by pattern
nterm-cli devices -f "Lab-ENG"             # Filter by folder
nterm-cli search 192.168                   # Search by IP prefix
nterm-cli device eng-leaf-1                # Specific device

# Credential queries (interactive unlock)
nterm-cli credentials --unlock
nterm-cli credential lab-admin -u
nterm-cli resolve 192.168.1.1 -u

# Credential queries (password via argument - for scripts)
nterm-cli credentials --password "$VAULT_PASS"

# JSON output for scripting
nterm-cli --json devices | jq '.[].hostname'
nterm-cli --json search leaf | jq -r '.[] | "\(.name)\t\(.hostname)"'
```

---

## Architecture

```
nterm/scripting/
├── __init__.py      # Exports: NTermAPI, api, DeviceInfo, CredentialInfo
├── api.py           # Core API implementation
└── cli.py           # Click-based CLI wrapper

nterm/session/
└── local_terminal.py    # IPython integration with API auto-load
```

The API wraps two existing nterm components:

- **SessionStore** (`nterm.manager.models`) - SQLite-backed device/session inventory
- **CredentialResolver** (`nterm.vault.resolver`) - Encrypted credential vault

### Design Principles

1. **Read-only credential access** - The API exposes credential metadata but never raw secrets. Secrets stay inside the resolver for actual connections.

2. **Same data, three interfaces** - IPython, CLI, and direct Python all use identical `NTermAPI` methods.

3. **Vault-aware** - Credential operations require explicit unlock. Lock state is preserved across calls.

4. **JSON-friendly** - All dataclasses have `.to_dict()` for serialization. CLI has `--json` flag.

---

## Roadmap

### Connection & Command Execution (Planned)

```python
# Connect to device
session = api.connect("eng-leaf-1")
session = api.connect("192.168.1.1", credential="lab-admin")

# Execute commands
output = api.send(session, "show ip route")
output = api.send_config(session, ["interface gi0/1", "description UPLINK"])

# Batch operations
results = api.batch("show version", devices="eng-*")
for device, output in results.items():
    print(f"{device}: {output.splitlines()[0]}")

# Disconnect
api.disconnect(session)
```

### MCP Tool Integration (Planned)

```python
@mcp_tool
def network_command(device: str, command: str) -> str:
    """Execute command on network device."""
    session = api.connect(device)
    try:
        return api.send(session, command)
    finally:
        api.disconnect(session)

@mcp_tool
def list_network_devices(pattern: str = "*") -> list[dict]:
    """List available network devices."""
    return [d.to_dict() for d in api.devices(pattern)]
```

### CLI Extensions (Planned)

```bash
# Execute commands
nterm-cli exec eng-leaf-1 "show version"
nterm-cli exec -p "eng-*" "show ip int brief"

# Batch with output
nterm-cli batch --devices "lab-*" --command "show version" --output results/
```

---

## Examples

### Export Device Inventory

```python
import json
from nterm.scripting import api

inventory = {
    "devices": [d.to_dict() for d in api.devices()],
    "folders": api.folders(),
}

with open("inventory.json", "w") as f:
    json.dump(inventory, f, indent=2)
```

### Find Devices Without Credentials

```python
from nterm.scripting import api

for device in api.devices():
    if not device.credential:
        print(f"No credential: {device.name} ({device.hostname})")
```

### Audit Credential Coverage

```python
from nterm.scripting import api

api.unlock("vault-password")

for device in api.devices():
    match = api.resolve_credential(device.hostname)
    status = f"→ {match}" if match else "NO MATCH"
    print(f"{device.hostname:20} {status}")
```

### Shell Script Integration

```bash
#!/bin/bash
# Check which devices are in a specific folder

FOLDER="Lab-ENG"
DEVICES=$(nterm-cli --json devices -f "$FOLDER" | jq -r '.[].hostname')

for host in $DEVICES; do
    echo "Pinging $host..."
    ping -c 1 -W 1 "$host" > /dev/null && echo "  UP" || echo "  DOWN"
done
```

---

## Related

- [nterm](../README.md) - Main terminal application
- [Credential Vault](../vault/README.md) - Encrypted credential storage
- [Session Manager](../manager/README.md) - Device inventory UI