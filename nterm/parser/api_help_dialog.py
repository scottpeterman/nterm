"""
nterm API Help Dialog

Shows API usage, examples, and workflows for the scripting interface.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget,
    QTextEdit, QPushButton, QLabel, QWidget, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class APIHelpDialog(QDialog):
    """Dialog showing nterm API documentation and examples."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("nterm API Help")
        self.setMinimumSize(900, 700)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Header
        header = QLabel("nterm Scripting API")
        header_font = QFont()
        header_font.setPointSize(16)
        header_font.setBold(True)
        header.setFont(header_font)
        layout.addWidget(header)

        subtitle = QLabel("Programmatic network automation from IPython, Python scripts, or as the foundation for MCP tools")
        layout.addWidget(subtitle)

        layout.addSpacing(10)

        # Tabs
        tabs = QTabWidget()
        tabs.addTab(self._create_overview_tab(), "Overview")
        tabs.addTab(self._create_quickstart_tab(), "Quick Start")
        tabs.addTab(self._create_reference_tab(), "API Reference")
        tabs.addTab(self._create_platform_tab(), "Platform Commands")
        tabs.addTab(self._create_examples_tab(), "Examples")
        tabs.addTab(self._create_troubleshooting_tab(), "Troubleshooting")
        layout.addWidget(tabs)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        copy_btn = QPushButton("Copy Sample Code")
        copy_btn.clicked.connect(self._copy_sample_code)
        btn_layout.addWidget(copy_btn)

        close_btn = QPushButton("Close")
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _create_overview_tab(self) -> QWidget:
        """Create overview tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setMarkdown("""
# nterm Scripting API

Programmatic network automation from IPython, Python scripts, or as the foundation for MCP tools and agentic workflows.

Connect to devices, execute commands, and get structured data back - all using your existing nterm sessions and encrypted credentials.

## Features

**Connection Management**
- Auto-credential resolution from encrypted vault
- Platform auto-detection (Cisco IOS/NX-OS/IOS-XE/XR, Arista EOS, Juniper)
- **Context manager** for automatic cleanup (`with api.session()`)
- Legacy device support (RSA SHA-1 fallback)
- Jump host support built-in
- Connection pooling and tracking

**Structured Data**
- **961 TextFSM templates** from networktocode/ntc-templates
- Automatic command parsing - raw text → List[Dict]
- **Platform-aware commands** - one call, correct syntax
- Field normalization across vendors
- Fallback to raw output if parsing fails

**Developer Tools**
- Rich dataclasses with tab completion
- `debug_parse()` for troubleshooting parsing
- `db_info()` for database diagnostics
- `disconnect_all()` for cleanup
- Comprehensive help system (F1 in GUI)

## Accessing the API

The API is pre-loaded in IPython sessions:

1. **Dev → IPython → Open in Tab**
2. The `api` object is automatically available
3. Use `api.help()` to see all commands

## Prerequisites

**TextFSM Template Database**

Required for command parsing. Download via GUI:

- **Dev → Download NTC Templates...**
- Click **Fetch Available Platforms**
- Select platforms (cisco_ios, arista_eos, etc.)
- Click **Download Selected**

**Credential Vault**

Store device credentials securely:

- **Edit → Credential Manager...**
- Create credentials with pattern matching
- Unlock vault: `api.unlock("password")`
""")
        layout.addWidget(text)
        return widget

    def _create_quickstart_tab(self) -> QWidget:
        """Create quick start tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setFont(QFont("Courier", 10))
        text.setText("""# Quick Start - Context Manager (Recommended)

# 1. Unlock vault
api.unlock("vault-password")

# 2. List your devices
api.devices()
# [Device(wan-core-1, 172.16.128.1:22, cred=home_lab), ...]

# 3. Connect with context manager (auto-disconnects)
with api.session("wan-core-1") as session:
    result = api.send(session, "show version")
    print(result.parsed_data)
    # [{'VERSION': '15.2(4)M11', 'HOSTNAME': 'wan-core-1', ...}]
# Session automatically closed here


# Platform-Aware Commands

with api.session("wan-core-1") as s:
    # Automatically uses correct syntax for platform
    result = api.send_platform_command(s, 'config', parse=False)
    print(f"Config: {len(result.raw_output)} bytes")
    
    # Get version info
    result = api.send_platform_command(s, 'version')
    
    # Get BGP summary (works on Cisco, Arista, Juniper)
    result = api.send_platform_command(s, 'bgp_summary')


# Try Multiple Commands (CDP/LLDP discovery)

with api.session("wan-core-1") as s:
    # Try CDP first, fall back to LLDP
    result = api.send_first(s, [
        "show cdp neighbors detail",
        "show lldp neighbors detail",
    ])
    
    if result and result.parsed_data:
        for neighbor in result.parsed_data:
            print(f"{neighbor.get('NEIGHBOR', 'unknown')}")


# Multi-Device Workflow

for device in api.devices("spine-*"):
    with api.session(device.name) as s:
        result = api.send(s, "show version")
        
        if result.parsed_data:
            version = result.parsed_data[0]['VERSION']
            print(f"{device.name}: {version}")
# Sessions auto-disconnect when exiting context


# Manual Connection (requires explicit disconnect)

session = api.connect("device-name")
result = api.send(session, "show version")
api.disconnect(session)

# Cleanup all sessions
count = api.disconnect_all()
print(f"Disconnected {count} session(s)")
""")
        layout.addWidget(text)
        return widget

    def _create_reference_tab(self) -> QWidget:
        """Create API reference tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setFont(QFont("Courier", 9))
        text.setText("""# API Reference

## Device Operations

api.devices()                     # List all devices
api.devices("pattern*")           # Filter by glob pattern
api.devices(folder="Lab-ENG")     # Filter by folder
api.search("query")               # Search by name/hostname/description
api.device("name")                # Get specific device
api.folders()                     # List all folders

DeviceInfo fields: name, hostname, port, folder, credential,
                   last_connected, connect_count

## Credential Operations (requires unlocked vault)

api.unlock("password")            # Unlock vault
api.lock()                        # Lock vault
api.credentials()                 # List credentials (no secrets)
api.credentials("*admin*")        # Filter by pattern
api.credential("name")            # Get specific credential
api.resolve_credential("host")    # Find matching credential

Properties:
api.vault_initialized             # Vault exists
api.vault_unlocked                # Vault is unlocked

CredentialInfo fields: name, username, has_password, has_key,
                       match_hosts, match_tags, is_default

## Connection Operations

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
api.active_sessions()             # List open connections

## Command Execution

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
result.parse_template             # Template used
result.timestamp                  # When command was run
result.to_dict()                  # Export as dictionary

## Platform-Aware Commands (NEW)

# Automatically uses correct syntax for detected platform
result = api.send_platform_command(session, 'config', parse=False)
result = api.send_platform_command(session, 'version')
result = api.send_platform_command(session, 'interfaces_status')
result = api.send_platform_command(session, 'interface_detail', name='Gi0/1')
result = api.send_platform_command(session, 'bgp_summary')
result = api.send_platform_command(session, 'routing_table')

# See "Platform Commands" tab for full list

## Try Multiple Commands (NEW)

# Try commands in order until one succeeds
result = api.send_first(session, [
    "show cdp neighbors detail",
    "show lldp neighbors detail",
])

# Options
result = api.send_first(
    session,
    commands,
    parse=True,              # Attempt parsing
    timeout=30,              # Per-command timeout
    require_parsed=True,     # Only succeed if parsed_data is non-empty
)

## Debugging

api.debug_parse(cmd, output, platform)  # Debug parsing issues
api.db_info()                           # Database diagnostics
api.status()                            # API summary
api.help()                              # Show all commands
""")
        layout.addWidget(text)
        return widget

    def _create_platform_tab(self) -> QWidget:
        """Create platform commands tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setMarkdown("""
# Platform-Aware Commands

The `send_platform_command()` method automatically uses the correct syntax for the detected platform.

## Supported Platforms

Auto-detected from `show version` output:

- `cisco_ios` - Cisco IOS
- `cisco_nxos` - Cisco Nexus NX-OS
- `cisco_iosxe` - Cisco IOS-XE
- `cisco_iosxr` - Cisco IOS-XR
- `arista_eos` - Arista EOS
- `juniper_junos` - Juniper Junos

## Available Command Types

| Command Type | Cisco IOS | Arista EOS | Juniper |
|--------------|-----------|------------|---------|
| `config` | show running-config | show running-config | show configuration |
| `version` | show version | show version | show version |
| `interfaces` | show interfaces | show interfaces | show interfaces |
| `interfaces_status` | show interfaces status | show interfaces status | show interfaces terse |
| `interface_detail` | show interfaces {name} | show interfaces {name} | show interfaces {name} |
| `neighbors_cdp` | show cdp neighbors detail | show lldp neighbors detail | - |
| `neighbors_lldp` | show lldp neighbors detail | show lldp neighbors detail | show lldp neighbors |
| `neighbors` | show cdp neighbors detail | show lldp neighbors detail | show lldp neighbors |
| `routing_table` | show ip route | show ip route | show route |
| `bgp_summary` | show ip bgp summary | show ip bgp summary | show bgp summary |
| `bgp_neighbors` | show ip bgp neighbors | show ip bgp neighbors | show bgp neighbor |

## Usage Examples

```python
# Get running config (works on any platform)
result = api.send_platform_command(session, 'config', parse=False)

# Get version info
result = api.send_platform_command(session, 'version')

# Get interface status
result = api.send_platform_command(session, 'interfaces_status')

# Get specific interface
result = api.send_platform_command(session, 'interface_detail', name='Gi0/1')

# Get BGP summary
result = api.send_platform_command(session, 'bgp_summary')

# Get routing table
result = api.send_platform_command(session, 'routing_table')
```

## Try Multiple Commands

For discovery across platforms with different capabilities:

```python
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
```

## Template Coverage

**961 TextFSM templates** available for 69 platforms via ntc-templates.

Download additional templates via:
**Dev → Download NTC Templates...**
""")
        layout.addWidget(text)
        return widget

    def _create_examples_tab(self) -> QWidget:
        """Create examples tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setFont(QFont("Courier", 9))
        text.setText("""# Examples

# Example 1: Collect Software Versions (Context Manager)
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


# Example 2: CDP/LLDP Neighbor Discovery
with api.session("wan-core-1") as s:
    # Automatically tries CDP then LLDP
    result = api.send_first(s, [
        "show cdp neighbors detail",
        "show lldp neighbors detail",
    ])
    
    if result and result.parsed_data:
        for neighbor in result.parsed_data:
            local_intf = neighbor.get('LOCAL_INTERFACE', 'unknown')
            remote = neighbor.get('NEIGHBOR', 'unknown')
            print(f"{remote:30} via {local_intf}")


# Example 3: Platform-Aware Config Backup
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

print(f"\\nBackups saved to: {backup_dir}")


# Example 4: Interface Error Report
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


# Example 5: Device Inventory CSV
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


# Example 6: Multi-Device BGP Summary
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


# Example 7: Cleanup All Sessions
# At end of script or in finally block
count = api.disconnect_all()
print(f"Disconnected {count} session(s)")
""")
        layout.addWidget(text)
        return widget

    def _create_troubleshooting_tab(self) -> QWidget:
        """Create troubleshooting tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setMarkdown("""
# Troubleshooting

## Database Not Found

**Error:** `RuntimeError: Failed to initialize TextFSM engine`

**Solution:**
1. Go to **Dev → Download NTC Templates...**
2. Click **Fetch Available Platforms**
3. Select platforms you need
4. Click **Download Selected**
5. Restart IPython session

**Verify:**
```python
api.db_info()
# {'db_exists': True, 'db_size_mb': 0.3, ...}
```

## Vault Locked

**Error:** `RuntimeError: Vault is locked`

**Solution:**
```python
api.unlock("your-vault-password")
```

**Check status:**
```python
api.vault_unlocked  # Returns True/False
```

## No Credentials

**Error:** `ValueError: No credentials available for hostname`

**Solution:**
1. Go to **Edit → Credential Manager...**
2. Add credential with host pattern matching
3. Unlock vault and try again

**Debug:**
```python
api.credentials()  # List all credentials
api.resolve_credential("192.168.1.1")  # Check which would match
```

## Parsing Failed

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
result = api.send(session, "show version", parse=False)
print(result.raw_output)
```

## Paging Not Disabled

**Error:** `PagingNotDisabledError: Paging prompt '--More--' detected`

**Cause:** Terminal paging wasn't disabled before command execution.

This indicates a problem with platform detection or session setup. The API automatically sends `terminal length 0` (or equivalent) after connecting.

**Debug:**
```python
# Check platform was detected
print(session.platform)  # Should not be None

# Try with debug enabled
session = api.connect("device", debug=True)
```

## Connection Failed

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

## Platform Not Detected

**Symptom:** `session.platform` is `None`

Platform detection looks for keywords in `show version` output:
- Cisco IOS: "Cisco IOS Software"
- Cisco NX-OS: "Cisco Nexus Operating System"
- Arista: "Arista", "vEOS"
- Juniper: "JUNOS"

If not detected, parsing won't work automatically.

**Debug:**
```python
session = api.connect("device")
print(session.platform)  # None

# Check show version output
result = api.send(session, "show version", parse=False)
print(result.raw_output[:500])
```

## Session Stuck

**Symptom:** Command hangs or times out

**Solutions:**
```python
# Increase timeout
result = api.send(session, "show tech-support", timeout=120)

# Check if session still active
session.is_connected()

# Disconnect and reconnect
api.disconnect(session)
session = api.connect("device")

# Or cleanup all
api.disconnect_all()
```

## Getting Help

**In IPython:**
```python
api.help()           # Show all commands
api.status()         # API status summary
api.db_info()        # Database diagnostics

# Object inspection
session?             # Show ActiveSession help
result?              # Show CommandResult help
```

**From GUI:**
- **Dev → API Help...** (this dialog)
- **Dev → Download NTC Templates...**
- **Edit → Credential Manager...**
- Press **F1** for comprehensive help
""")
        layout.addWidget(text)
        return widget

    def _copy_sample_code(self):
        """Copy sample code to clipboard."""
        sample = """# nterm API Quick Start

# Unlock vault
api.unlock("vault-password")

# List devices
devices = api.devices()

# Connect with context manager (recommended)
with api.session("device-name") as s:
    # Execute command with parsing
    result = api.send(s, "show version")
    
    # Access parsed data
    if result.parsed_data:
        print(result.parsed_data[0])
    else:
        print(result.raw_output)
    
    # Platform-aware command
    config = api.send_platform_command(s, 'config', parse=False)
    print(f"Config size: {len(config.raw_output)} bytes")

# Session auto-disconnects when exiting 'with' block

# Manual connection (if needed)
session = api.connect("other-device")
result = api.send(session, "show interfaces")
api.disconnect(session)

# Cleanup all sessions
api.disconnect_all()
"""
        from PyQt6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(sample)

        QMessageBox.information(
            self,
            "Copied",
            "Sample code copied to clipboard!\n\nPaste into IPython to get started."
        )