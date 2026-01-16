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

# Context manager (recommended) - auto-disconnects
with api.session("wan-core-1") as session:
    result = api.send(session, "show version")
    print(result.parsed_data)
    # [{'VERSION': '15.2(4)M11', 'HOSTNAME': 'wan-core-1', ...}]

# Platform-aware commands
with api.session("wan-core-1") as s:
    # Automatically uses correct syntax for platform
    result = api.send_platform_command(s, 'config', parse=False)
    print(f"Config: {len(result.raw_output)} bytes")
```

### From Python Scripts

```python
from nterm.scripting import NTermAPI

api = NTermAPI()
api.unlock("vault-password")

# Multi-device workflow with context manager
for device in api.devices("spine-*"):
    with api.session(device.name) as s:
        result = api.send(s, "show version")
        
        if result.parsed_data:
            version = result.parsed_data[0]['VERSION']
            print(f"{device.name}: {version}")
# Sessions auto-disconnect when exiting context
```

---

## Features

### 🔌 Connection Management
- Auto-credential resolution from encrypted vault
- Platform auto-detection (Cisco IOS/NX-OS/IOS-XE/XR, Arista EOS, Juniper)
- **Context manager** for automatic cleanup (`with api.session()`)
- Legacy device support (RSA SHA-1 fallback)
- Jump host support built-in
- Connection pooling and tracking

### 📊 Structured Data
- **961 TextFSM templates** from networktocode/ntc-templates
- Automatic command parsing - raw text → List[Dict]
- **Platform-aware commands** - one call, correct syntax
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
- `disconnect_all()` for cleanup
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
# {'db_exists': True, 'db_size_mb': 0.3, ...}
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
pip install ntermqt[scripting]
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
# Context manager (recommended) - auto-disconnects on exit
with api.session("device-name") as session:
    result = api.send(session, "show version")
# Session automatically closed here

# Manual connection (requires explicit disconnect)
session = api.connect("device-name")
session = api.connect("device", credential="cred-name")
session = api.connect("192.168.1.1", debug=True)

# Session attributes
session.device_name               # Device name
session.hostname                  # IP/hostname
session.platform                  # 'cisco_ios', 'arista_eos', etc.
session.prompt                    # Device prompt
session.is_connected()            # Check if active
session.connected_at              # Timestamp

# Disconnect
api.disconnect(session)           # Single session
api.disconnect_all()              # All active sessions
api.active_sessions()             # List open connections (List[ActiveSession])
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

### Platform-Aware Commands (NEW)

```python
# Automatically uses correct syntax for detected platform
# Works across Cisco IOS, NX-OS, Arista EOS, Juniper, etc.

# Get running config (uses 'show run' vs 'show configuration' as appropriate)
result = api.send_platform_command(session, 'config', parse=False)

# Get version info
result = api.send_platform_command(session, 'version')

# Get interface status
result = api.send_platform_command(session, 'interfaces_status')

# Get specific interface details
result = api.send_platform_command(session, 'interface_detail', name='Gi0/1')

# Get BGP summary
result = api.send_platform_command(session, 'bgp_summary')

# Get routing table
result = api.send_platform_command(session, 'routing_table')

# Available command types:
# - config, version, interfaces, interfaces_status, interface_detail
# - neighbors_cdp, neighbors_lldp, neighbors
# - routing_table, bgp_summary, bgp_neighbors
```

### Try Multiple Commands (NEW)

```python
# Try commands in order until one succeeds
# Perfect for CDP/LLDP discovery, platform variations

# Try CDP first, fall back to LLDP
result = api.send_first(session, [
    "show cdp neighbors detail",
    "show lldp neighbors detail",
])

# Platform-agnostic config fetch
result = api.send_first(session, [
    "show running-config",
    "show configuration",
], parse=False, require_parsed=False)

# Options
result = api.send_first(
    session,
    commands,
    parse=True,              # Attempt parsing
    timeout=30,              # Per-command timeout
    require_parsed=True,     # Only succeed if parsed_data is non-empty
)
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
#   'db_size_mb': 0.3,
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

### Example 1: Collect Software Versions (Context Manager)

```python
api.unlock("password")
versions = {}

for device in api.devices():
    try:
        with api.session(device.name) as s:
            result = api.send(s, "show version")
            
            if result.parsed_data:
                ver = result.parsed_data[0].get('VERSION', 'unknown')
                versions[device.name] = ver
    except Exception as e:
        print(f"Failed on {device.name}: {e}")

# Print results
for name, ver in sorted(versions.items()):
    print(f"{name:20} {ver}")
```

### Example 2: CDP/LLDP Neighbor Discovery

```python
with api.session("wan-core-1") as s:
    # Automatically tries CDP then LLDP
    result = api.send_first(s, [
        "show cdp neighbors detail",
        "show lldp neighbors detail",
    ])
    
    if result and result.parsed_data:
        for neighbor in result.parsed_data:
            print(f"{neighbor.get('NEIGHBOR', 'unknown'):30} via {neighbor.get('LOCAL_INTERFACE', 'unknown')}")
```

### Example 3: Platform-Aware Config Backup

```python
from pathlib import Path
from datetime import datetime

api.unlock("password")
backup_dir = Path("config_backups")
backup_dir.mkdir(exist_ok=True)

for device in api.devices(folder="Production"):
    try:
        with api.session(device.name) as s:
            # Works on Cisco, Arista, Juniper - picks correct command
            result = api.send_platform_command(s, 'config', parse=False)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = backup_dir / f"{device.name}_{timestamp}.cfg"
            filename.write_text(result.raw_output)
            
            print(f"✓ {device.name}: {len(result.raw_output)} bytes")
    except Exception as e:
        print(f"✗ {device.name}: {e}")

print(f"\nBackups saved to: {backup_dir}")
```

### Example 4: Interface Error Report

```python
with api.session("distribution-1") as s:
    result = api.send(s, "show interfaces")
    
    if result.parsed_data:
        errors_found = False
        for intf in result.parsed_data:
            in_errors = int(intf.get('in_errors', 0) or 0)
            out_errors = int(intf.get('out_errors', 0) or 0)
            
            if in_errors > 0 or out_errors > 0:
                errors_found = True
                print(f"{intf['interface']:15} IN: {in_errors:>8}  OUT: {out_errors:>8}")
        
        if not errors_found:
            print("No interface errors found")
```

### Example 5: Device Inventory CSV

```python
import csv
from nterm.scripting.platform_utils import extract_version_info

api.unlock("password")

with open('inventory.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['Device', 'IP', 'Platform', 'Version', 'Serial', 'Uptime'])
    
    for device in api.devices():
        try:
            with api.session(device.name) as s:
                result = api.send_platform_command(s, 'version')
                
                if result and result.parsed_data:
                    # Extract normalized version info
                    info = extract_version_info(result.parsed_data, s.platform)
                    writer.writerow([
                        device.name,
                        device.hostname,
                        s.platform,
                        info.get('version', ''),
                        info.get('serial', ''),
                        info.get('uptime', ''),
                    ])
                else:
                    writer.writerow([device.name, device.hostname, s.platform, '', '', ''])
        except Exception as e:
            writer.writerow([device.name, device.hostname, 'ERROR', str(e), '', ''])

print("Inventory saved to inventory.csv")
```

### Example 6: Multi-Device BGP Summary

```python
api.unlock("password")
bgp_report = {}

for device in api.devices("*spine*"):
    try:
        with api.session(device.name) as s:
            result = api.send_platform_command(s, 'bgp_summary')
            
            if result and result.parsed_data:
                neighbor_count = len(result.parsed_data)
                established = sum(1 for n in result.parsed_data 
                                  if str(n.get('STATE_PFXRCD', '')).isdigit())
                bgp_report[device.name] = {
                    'total': neighbor_count,
                    'established': established,
                }
    except Exception as e:
        bgp_report[device.name] = {'error': str(e)}

# Print report
print(f"{'Device':<25} {'Total':<10} {'Established':<10}")
print("-" * 45)
for device, info in sorted(bgp_report.items()):
    if 'error' in info:
        print(f"{device:<25} ERROR: {info['error']}")
    else:
        print(f"{device:<25} {info['total']:<10} {info['established']:<10}")
```

### Example 7: Cleanup All Sessions

```python
# At end of script or in finally block
count = api.disconnect_all()
print(f"Disconnected {count} session(s)")
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

### Paging Not Disabled

**Error:** `PagingNotDisabledError: Paging prompt '--More--' detected`

**Cause:** Terminal paging wasn't disabled before command execution.

This error indicates a problem with platform detection or session setup. The API automatically sends `terminal length 0` (or equivalent) after connecting.

**Debug:**
```python
# Check platform was detected
print(session.platform)  # Should not be None

# Try with debug enabled
session = api.connect("device", debug=True)
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

# Enable debug mode
session = api.connect("device", debug=True)
```

### Platform Not Detected

**Symptom:** `session.platform` is `None`

Platform detection looks for keywords in `show version` output:
- Cisco IOS: "Cisco IOS Software"
- Cisco NX-OS: "Cisco Nexus Operating System"
- Arista: "Arista", "vEOS"
- Juniper: "JUNOS"

If not detected, parsing won't work automatically.

---

## Architecture

```
nterm/scripting/
├── __init__.py          # Exports: NTermAPI, api, DeviceInfo, CredentialInfo
├── api.py               # Core API - connect, send, session context manager
├── models.py            # ActiveSession, CommandResult, DeviceInfo, CredentialInfo
├── platform_data.py     # Platform commands, patterns, field mappings
├── platform_utils.py    # detect_platform, get_platform_command, extract_*
├── ssh_connection.py    # Low-level SSH, ANSI filtering, prompt detection
├── repl.py              # Interactive REPL (NTermREPL)
└── repl_interactive.py  # REPL display and formatting

Integration Points:
├── nterm.manager.models.SessionStore      # Device inventory (SQLite)
├── nterm.vault.resolver.CredentialResolver # Encrypted credentials
├── nterm.parser.tfsm_fire.TextFSMAutoEngine # Command parsing
└── nterm.session.local_terminal.LocalTerminal.ipython() # IPython with API
```

### Design Principles

1. **Structured Data First** - Commands return parsed data (List[Dict]), not raw text
2. **Automatic Platform Detection** - No manual configuration needed
3. **Platform-Aware Commands** - One API, correct syntax everywhere
4. **Secure by Default** - Credentials stay encrypted, secrets never exposed
5. **Fail Gracefully** - Parsing failures fallback to raw output
6. **Developer Friendly** - Context managers, rich objects, tab completion

---

## Platform Support

Auto-detected platforms:
- `cisco_ios` - Cisco IOS
- `cisco_nxos` - Cisco Nexus NX-OS
- `cisco_iosxe` - Cisco IOS-XE
- `cisco_iosxr` - Cisco IOS-XR
- `arista_eos` - Arista EOS
- `juniper_junos` - Juniper Junos

**Platform-aware command types:**

| Command Type | Cisco IOS | Arista EOS | Juniper |
|--------------|-----------|------------|---------|
| `config` | show running-config | show running-config | show configuration |
| `version` | show version | show version | show version |
| `interfaces_status` | show interfaces status | show interfaces status | show interfaces terse |
| `neighbors` | show cdp neighbors detail | show lldp neighbors detail | show lldp neighbors |
| `bgp_summary` | show ip bgp summary | show ip bgp summary | show bgp summary |
| `routing_table` | show ip route | show ip route | show route |

Templates available for 69 platforms via ntc-templates. Download via:
**Dev → Download NTC Templates...**

---

## MCP Integration (Future)

Foundation for Model Context Protocol tools:

```python
@mcp_tool
def network_command(device: str, command: str) -> dict:
    """Execute command on network device."""
    with api.session(device) as s:
        result = api.send(s, command)
        return result.to_dict()

@mcp_tool
def get_device_version(device: str) -> dict:
    """Get device version info."""
    with api.session(device) as s:
        result = api.send_platform_command(s, 'version')
        return extract_version_info(result.parsed_data, s.platform)

@mcp_tool  
def discover_neighbors(device: str) -> list[dict]:
    """Discover CDP/LLDP neighbors."""
    with api.session(device) as s:
        result = api.send_first(s, [
            "show cdp neighbors detail",
            "show lldp neighbors detail",
        ])
        return result.parsed_data if result else []

@mcp_tool
def list_devices(pattern: str = "*") -> list[dict]:
    """List available network devices."""
    return [d.to_dict() for d in api.devices(pattern)]
```

---

## Related Documentation

- [nterm GUI](../README.md) - Main terminal application
- [REPL Documentation](README_REPL.md) - Interactive REPL interface
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