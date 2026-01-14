# nterm Scripting API

Programmatic network automation from IPython, Python scripts, or as the foundation for MCP tools and agentic workflows.

Connect to devices, execute commands, and get structured data back - all using your existing nterm sessions and encrypted credentials.

---

## Quick Start

### In nterm IPython

Open **Dev → IPython → Open in Tab** and the API is pre-loaded:

```python
# Unlock vault and connect
api.unlock("vault-password")
session = api.connect("wan-core-1")

# Execute command - returns parsed data
result = api.send(session, "show version")
print(result.parsed_data)
# [{'VERSION': '15.2(4)M11', 'HOSTNAME': 'wan-core-1', ...}]

# More commands
result = api.send(session, "show cdp neighbors")
for neighbor in result.parsed_data:
    print(f"{neighbor['NEIGHBOR_NAME']} via {neighbor['LOCAL_INTERFACE']}")

# Disconnect
api.disconnect(session)
```

### From Python Scripts

```python
from nterm.scripting import NTermAPI

api = NTermAPI()
api.unlock("vault-password")

# Multi-device workflow
for device in api.devices("spine-*"):
    session = api.connect(device.name)
    result = api.send(session, "show version")
    
    if result.parsed_data:
        version = result.parsed_data[0]['VERSION']
        print(f"{device.name}: {version}")
    
    api.disconnect(session)
```

---

## Features

### 🔌 Connection Management
- Auto-credential resolution from encrypted vault
- Platform auto-detection (Cisco IOS/NX-OS/IOS-XE/XR, Arista EOS, Juniper)
- Legacy device support (RSA SHA-1 fallback)
- Jump host support built-in
- Connection pooling and tracking

### 📊 Structured Data
- **961 TextFSM templates** from networktocode/ntc-templates
- Automatic command parsing - raw text → List[Dict]
- Field normalization across vendors
- Match scoring for debugging
- Fallback to raw output if parsing fails

### 🔐 Security
- Encrypted credential vault
- Pattern-based credential matching
- No secrets in API responses
- Same security as GUI connections

### 🛠️ Developer Tools
- Rich dataclasses with tab completion
- `debug_parse()` for troubleshooting parsing
- `db_info()` for database diagnostics
- Connection status tracking
- Comprehensive help system (F1 in GUI)

---

## Prerequisites

### TextFSM Template Database

**Required for command parsing.** Download via GUI:

1. **Dev → Download NTC Templates...**
2. Click **Fetch Available Platforms**
3. Select platforms (cisco_ios, arista_eos, etc.)
4. Click **Download Selected**

Or verify existing database:
```python
api.db_info()
# {'db_exists': True, 'db_size_mb': 52.92, ...}
```

### Credential Vault

Store device credentials via **Edit → Credential Manager...**

```python
# Unlock vault
api.unlock("vault-password")

# List available credentials
api.credentials()
# [Credential(lab-admin, user=cisco, auth=password), ...]
```

---

## Installation

Included with nterm. For standalone use:

```bash
pip install nterm
```

Dependencies:
- `paramiko` - SSH connections
- `textfsm` - Command parsing
- `cryptography` - Credential vault
- `ipython` - Interactive shell (optional)

---

## API Reference

### Device Operations

```python
api.devices()                     # List all devices
api.devices("pattern*")           # Filter by glob pattern
api.devices(folder="Lab-ENG")     # Filter by folder
api.search("query")               # Search by name/hostname/description
api.device("name")                # Get specific device
api.folders()                     # List all folders
```

**DeviceInfo fields:**
- `name`, `hostname`, `port`, `folder`
- `credential`, `last_connected`, `connect_count`

### Credential Operations

```python
api.unlock("password")            # Unlock vault
api.lock()                        # Lock vault
api.credentials()                 # List credentials (no secrets)
api.credentials("*admin*")        # Filter by pattern
api.credential("name")            # Get specific credential
api.resolve_credential("host")    # Find matching credential

# Properties
api.vault_initialized             # Vault exists
api.vault_unlocked                # Vault is unlocked
```

**CredentialInfo fields:**
- `name`, `username`, `has_password`, `has_key`
- `match_hosts`, `match_tags`, `is_default`

### Connection Operations

```python
# Connect (auto-detects platform)
session = api.connect("device-name")
session = api.connect("device", credential="cred-name")
session = api.connect("192.168.1.1")

# Session attributes
session.device_name               # Device name
session.hostname                  # IP/hostname
session.platform                  # 'cisco_ios', 'arista_eos', etc.
session.prompt                    # Device prompt
session.is_connected()            # Check if active (returns 1/0)
session.connected_at              # Timestamp

# Disconnect
api.disconnect(session)
api.active_sessions()             # List open connections
```

### Command Execution

```python
# Execute with parsing (default)
result = api.send(session, "show version")
result = api.send(session, "show interfaces")

# Options
result = api.send(session, "cmd", parse=False)        # Raw output only
result = api.send(session, "cmd", timeout=60)         # Custom timeout
result = api.send(session, "cmd", normalize=False)    # Keep vendor field names

# Result attributes
result.command                    # Command that was run
result.raw_output                 # Raw text from device
result.parsed_data                # List[Dict] or None
result.platform                   # Detected platform
result.parse_success              # Whether parsing worked
result.parse_template             # Template used (e.g., 'cisco_ios_show_version')
result.timestamp                  # When command was run
result.to_dict()                  # Export as dictionary
```

### Debugging

```python
# Troubleshoot parsing failures
debug = api.debug_parse(
    command="show version",
    output=result.raw_output,
    platform=session.platform
)

# Shows: template_used, best_score, all_scores, error
print(debug)

# Database diagnostics
api.db_info()
# {
#   'db_path': './tfsm_templates.db',
#   'db_exists': True,
#   'db_size_mb': 52.92,
#   'db_absolute_path': '/full/path/to/tfsm_templates.db',
#   ...
# }

# API summary
api.status()
# {
#   'devices': 14,
#   'folders': 3,
#   'credentials': 3,
#   'vault_unlocked': True,
#   'active_sessions': 1,
#   'parser_available': True,
#   ...
# }

# Show all commands
api.help()
```

---

## Examples

### Example 1: Collect Software Versions

```python
api.unlock("password")
versions = {}

for device in api.devices():
    try:
        session = api.connect(device.name)
        result = api.send(session, "show version")
        
        if result.parsed_data:
            ver = result.parsed_data[0].get('VERSION', 'unknown')
            versions[device.name] = ver
        
        api.disconnect(session)
    except Exception as e:
        print(f"Failed on {device.name}: {e}")

# Print results
for name, ver in sorted(versions.items()):
    print(f"{name:20} {ver}")
```

### Example 2: Find CDP Neighbors

```python
session = api.connect("wan-core-1")
result = api.send(session, "show cdp neighbors")

if result.parsed_data:
    for neighbor in result.parsed_data:
        print(f"{neighbor['NEIGHBOR_NAME']:30} via {neighbor['LOCAL_INTERFACE']}")
        
api.disconnect(session)

# Output:
# usa-rtr-1.lab.local            via Eth 1/1
# eng-rtr-1.lab.local            via Eth 1/2
```

### Example 3: Interface Status Report

```python
session = api.connect("core-switch")
result = api.send(session, "show ip interface brief")

print(f"{'Interface':<20} {'IP Address':<15} {'Status':<10} {'Protocol':<10}")
print("-" * 55)

if result.parsed_data:
    for intf in result.parsed_data:
        print(f"{intf['interface']:<20} "
              f"{intf['IP_ADDRESS']:<15} "
              f"{intf['STATUS']:<10} "
              f"{intf['PROTO']:<10}")

api.disconnect(session)
```

### Example 4: Check for Interface Errors

```python
session = api.connect("distribution-1")
result = api.send(session, "show interfaces")

if result.parsed_data:
    for intf in result.parsed_data:
        in_errors = int(intf.get('in_errors', 0))
        out_errors = int(intf.get('out_errors', 0))
        
        if in_errors > 0 or out_errors > 0:
            print(f"{intf['interface']:15} IN: {in_errors:>8}  OUT: {out_errors:>8}")

api.disconnect(session)
```

### Example 5: Configuration Backup

```python
import json
from datetime import datetime

api.unlock("password")
backups = {}

for device in api.devices(folder="Production"):
    try:
        session = api.connect(device.name)
        result = api.send(session, "show running-config", parse=False)
        
        backups[device.name] = {
            'hostname': device.hostname,
            'platform': session.platform,
            'config': result.raw_output,
            'timestamp': datetime.now().isoformat(),
        }
        
        api.disconnect(session)
    except Exception as e:
        print(f"Failed on {device.name}: {e}")

# Save to file
with open('backups.json', 'w') as f:
    json.dump(backups, f, indent=2)

print(f"Backed up {len(backups)} devices")
```

### Example 6: Device Inventory CSV

```python
import csv

api.unlock("password")

with open('inventory.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['Device', 'IP', 'Platform', 'Version', 'Serial', 'Uptime'])
    
    for device in api.devices():
        try:
            session = api.connect(device.name)
            result = api.send(session, "show version")
            
            if result.parsed_data:
                data = result.parsed_data[0]
                writer.writerow([
                    device.name,
                    device.hostname,
                    session.platform,
                    data.get('VERSION', ''),
                    data.get('SERIAL', [''])[0] if data.get('SERIAL') else '',
                    data.get('UPTIME', ''),
                ])
            
            api.disconnect(session)
        except Exception as e:
            writer.writerow([device.name, device.hostname, 'ERROR', str(e), '', ''])

print("Inventory saved to inventory.csv")
```

### Example 7: Multi-Device Command Execution

```python
def run_command_on_devices(command, pattern="*"):
    """Execute command on multiple devices, return results dict."""
    api.unlock("password")
    results = {}
    
    for device in api.devices(pattern):
        try:
            session = api.connect(device.name)
            result = api.send(session, command)
            results[device.name] = result
            api.disconnect(session)
        except Exception as e:
            results[device.name] = {'error': str(e)}
    
    return results

# Usage
results = run_command_on_devices("show version", pattern="spine-*")
for device, result in results.items():
    if hasattr(result, 'parsed_data') and result.parsed_data:
        ver = result.parsed_data[0].get('VERSION', 'unknown')
        print(f"{device}: {ver}")
```

---

## Troubleshooting

### Database Not Found

**Error:** `RuntimeError: Failed to initialize TextFSM engine`

**Solution:**
1. Download templates: **Dev → Download NTC Templates...**
2. Select platforms you need
3. Restart IPython session

**Verify:**
```python
api.db_info()
```

### Vault Locked

**Error:** `RuntimeError: Vault is locked`

**Solution:**
```python
api.unlock("your-vault-password")
```

### Parsing Failed

**Symptom:** `result.parsed_data` is `None`

**Debug:**
```python
result = api.send(session, "show version")

# Check raw output
print(result.raw_output[:200])

# Debug parsing
debug = api.debug_parse("show version", result.raw_output, session.platform)
print(debug)
# Shows: template_used, best_score, all_scores, error
```

**Common causes:**
- Template doesn't exist for this platform/command
- Platform not detected (check `session.platform`)
- Output format non-standard
- Database missing templates (download more)

**Workaround:**
```python
# Get raw output
result = api.send(session, "show version", parse=False)
print(result.raw_output)
```

### Connection Failed

**Debug:**
```python
# Check device info
device = api.device("device-name")
print(device)

# Try with different credential
session = api.connect("device", credential="other-cred")

# Check credentials
api.credentials()
api.resolve_credential("192.168.1.1")
```

### Platform Not Detected

**Symptom:** `session.platform` is `None`

Platform detection looks for keywords in `show version` output:
- Cisco: "Cisco IOS Software"
- Arista: "Arista", "vEOS"
- Juniper: "JUNOS"

If not detected, parsing won't work automatically.

---

## Architecture

```
nterm/scripting/
├── __init__.py      # Exports: NTermAPI, api, DeviceInfo, CredentialInfo
├── api.py           # Core API implementation
└── cli.py           # CLI wrapper (deprecated, use IPython)

Integration Points:
├── nterm.manager.models.SessionStore      # Device inventory (SQLite)
├── nterm.vault.resolver.CredentialResolver # Encrypted credentials
├── nterm.session.ssh.SSHSession           # SSH connections
├── nterm.parser.tfsm_fire.TextFSMAutoEngine # Command parsing
└── nterm.session.local_terminal.LocalTerminal.ipython() # IPython with API
```

### Design Principles

1. **Structured Data First** - Commands return parsed data (List[Dict]), not raw text
2. **Automatic Platform Detection** - No manual configuration needed
3. **Secure by Default** - Credentials stay encrypted, secrets never exposed
4. **Fail Gracefully** - Parsing failures fallback to raw output
5. **Developer Friendly** - Rich objects, tab completion, helpful errors

---

## Platform Support

Auto-detected platforms:
- `cisco_ios` - Cisco IOS
- `cisco_nxos` - Cisco Nexus NX-OS
- `cisco_iosxe` - Cisco IOS-XE
- `cisco_iosxr` - Cisco IOS-XR
- `arista_eos` - Arista EOS
- `juniper_junos` - Juniper Junos

Templates available for 69 platforms via ntc-templates. Download via:
**Dev → Download NTC Templates...**

---

## MCP Integration (Future)

Foundation for Model Context Protocol tools:

```python
@mcp_tool
def network_command(device: str, command: str) -> dict:
    """Execute command on network device."""
    session = api.connect(device)
    try:
        result = api.send(session, command)
        return result.to_dict()
    finally:
        api.disconnect(session)

@mcp_tool
def list_devices(pattern: str = "*") -> list[dict]:
    """List available network devices."""
    return [d.to_dict() for d in api.devices(pattern)]
```

---

## Related Documentation

- [nterm GUI](../README.md) - Main terminal application
- [API Help](api_help_dialog.py) - In-app documentation (F1)
- [Download Templates](ntc_download_dialog.py) - TextFSM template manager
- [Credential Vault](../vault/README.md) - Encrypted credential storage

---

## Support

**In nterm:**
- Press **F1** for comprehensive API help
- **Dev → API Help...** for examples and troubleshooting
- **Dev → Download NTC Templates...** for parser setup

**API Help:**
```python
api.help()           # Command reference
api.status()         # API status
api.db_info()        # Database diagnostics
```

---

## License

Same as nterm - see main repository