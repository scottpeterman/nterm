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

        subtitle = QLabel("Access your network devices programmatically from IPython")
        layout.addWidget(subtitle)

        layout.addSpacing(10)

        # Tabs
        tabs = QTabWidget()
        tabs.addTab(self._create_overview_tab(), "Overview")
        tabs.addTab(self._create_quickstart_tab(), "Quick Start")
        tabs.addTab(self._create_reference_tab(), "API Reference")
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

The nterm API provides programmatic access to your network devices from IPython.

## Features

**Device Management**
- Query saved devices and folders
- Search by name, hostname, or tags
- Access device metadata and connection history

**Secure Connections**
- Encrypted credential vault with pattern matching
- Auto-platform detection (Cisco, Arista, Juniper, etc.)
- Legacy device support (RSA SHA-1 fallback)
- Jump host support built-in

**Command Execution**
- Execute commands on network devices
- Automatic TextFSM parsing for structured data
- Field normalization across vendors
- Fallback to raw output if parsing fails

**Developer Tools**
- Rich data types with tab completion
- Debugging tools for parsing issues
- Database diagnostics
- Connection tracking

## Accessing the API

The API is pre-loaded in IPython sessions:

1. **Dev → IPython → Open in Tab**
2. The `api` object is automatically available
3. Use `api.help()` to see all commands

## Prerequisites

**TextFSM Template Database**

The API requires the TextFSM template database for parsing command output.

- Download via: **Dev → Download NTC Templates...**
- Select platforms you need (cisco_ios, arista_eos, etc.)
- Database stored as `tfsm_templates.db`

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
        text.setText("""# Quick Start - First Connection

# 1. Unlock vault
api.unlock("vault-password")

# 2. List your devices
api.devices()
# [Device(wan-core-1, 172.16.128.1:22, cred=home_lab), ...]

# 3. Connect to a device
session = api.connect("wan-core-1")
# <ActiveSession wan-core-1@172.16.128.1:22 connected, platform=cisco_ios>

# 4. Execute a command
result = api.send(session, "show version")

# 5. Access parsed data
print(result.parsed_data)
# [{'VERSION': '15.2(4)M11', 'HOSTNAME': 'wan-core-1', ...}]

# 6. Disconnect
api.disconnect(session)


# Common Workflows

# Search devices
devices = api.search("leaf")
devices = api.devices("eng-*")
devices = api.devices(folder="Lab-ENG")

# Connect with specific credential
session = api.connect("device", credential="lab-admin")

# Check connection status
if session.is_connected():
    result = api.send(session, "show ip route")

# Disable parsing for raw output
result = api.send(session, "show run", parse=False)
print(result.raw_output)

# Multi-device workflow
for device in api.devices("spine-*"):
    session = api.connect(device.name)
    result = api.send(session, "show version")
    if result.parsed_data:
        version = result.parsed_data[0]['VERSION']
        print(f"{device.name}: {version}")
    api.disconnect(session)
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
api.search("query")               # Search by name/hostname
api.device("name")                # Get specific device
api.folders()                     # List all folders

## Credential Operations (requires unlocked vault)

api.unlock("password")            # Unlock vault
api.lock()                        # Lock vault
api.credentials()                 # List all credentials
api.credentials("*admin*")        # Filter by pattern
api.credential("name")            # Get specific credential
api.resolve_credential("host")    # Find matching credential

## Connection Operations

session = api.connect("device")              # Connect and auto-detect
session = api.connect("device", "cred")      # Connect with credential
api.disconnect(session)                      # Close connection
api.active_sessions()                        # List open connections

## Command Execution

result = api.send(session, "show version")              # Execute and parse
result = api.send(session, "cmd", parse=False)          # Raw output only
result = api.send(session, "cmd", timeout=60)           # Custom timeout
result = api.send(session, "cmd", normalize=False)      # Don't normalize fields

## Result Access

result.raw_output                 # Raw text from device
result.parsed_data                # Parsed List[Dict] or None
result.platform                   # Detected platform
result.parse_success              # Whether parsing worked
result.parse_template             # Template used
result.to_dict()                  # Export as dictionary

## Session Attributes

session.device_name               # Device name
session.hostname                  # IP/hostname
session.port                      # SSH port
session.platform                  # Detected platform
session.prompt                    # Device prompt
session.is_connected()            # Check if active
session.connected_at              # Connection timestamp

## Debugging

api.debug_parse(cmd, output, platform)  # Debug parsing issues
api.db_info()                           # Database diagnostics
api.status()                            # API summary

## Status Properties

api.vault_unlocked                # Vault status (bool)
api.vault_initialized             # Vault exists (bool)
api._tfsm_engine                  # Parser instance
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

# Example 1: Collect Software Versions
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


# Example 2: Find Interfaces with Errors
session = api.connect("core-switch")
result = api.send(session, "show interfaces")

if result.parsed_data:
    for intf in result.parsed_data:
        in_errors = int(intf.get('in_errors', 0))
        out_errors = int(intf.get('out_errors', 0))

        if in_errors > 0 or out_errors > 0:
            print(f"{intf['interface']}: in={in_errors}, out={out_errors}")

api.disconnect(session)


# Example 3: Configuration Backup
import json
from datetime import datetime

backups = {}

for device in api.devices(folder="Production"):
    session = api.connect(device.name)
    result = api.send(session, "show running-config", parse=False)

    backups[device.name] = {
        'hostname': device.hostname,
        'config': result.raw_output,
        'timestamp': datetime.now().isoformat(),
    }

    api.disconnect(session)

# Save to file
with open('backups.json', 'w') as f:
    json.dump(backups, f, indent=2)


# Example 4: Audit Device Reachability
api.unlock("password")

print("Testing device connectivity...")
print(f"{'Device':<20} {'Status':<10} {'Platform':<15}")
print("-" * 45)

for device in api.devices():
    try:
        session = api.connect(device.name)
        platform = session.platform or 'unknown'
        print(f"{device.name:<20} {'UP':<10} {platform:<15}")
        api.disconnect(session)
    except Exception as e:
        print(f"{device.name:<20} {'DOWN':<10} {str(e)[:15]}")


# Example 5: Compare Configurations
session1 = api.connect("spine-1")
session2 = api.connect("spine-2")

config1 = api.send(session1, "show run", parse=False).raw_output
config2 = api.send(session2, "show run", parse=False).raw_output

# Find differences
lines1 = set(config1.split('\\n'))
lines2 = set(config2.split('\\n'))

print("Only in spine-1:")
for line in sorted(lines1 - lines2)[:10]:
    print(f"  {line}")

print("\\nOnly in spine-2:")
for line in sorted(lines2 - lines1)[:10]:
    print(f"  {line}")

api.disconnect(session1)
api.disconnect(session2)


# Example 6: Device Inventory Report
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
                    data.get('SERIAL', [''])[0],
                    data.get('UPTIME', ''),
                ])

            api.disconnect(session)
        except Exception as e:
            writer.writerow([device.name, device.hostname, 'ERROR', str(e), '', ''])

print("Inventory saved to inventory.csv")
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

**Check status:**
```python
api.db_info()
# Shows: db_path, db_exists, db_size
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

## Connection Failed

**Error:** Connection timeout or authentication failure

**Debug:**
```python
# Check device info
device = api.device("device-name")
print(device)

# Try with different credential
session = api.connect("device", credential="other-cred")

# Check if device is reachable
# (try from terminal first)
```

## Parsing Failed

**Symptom:** `result.parsed_data` is None but command succeeded

**Debug:**
```python
result = api.send(session, "show version")

# Check raw output
print(result.raw_output[:200])

# Debug parsing
debug = api.debug_parse(
    command="show version",
    output=result.raw_output,
    platform=session.platform
)

print(debug)
# Shows: template_used, best_score, all_scores, error
```

**Solutions:**
- Template might not exist for this command/platform
- Output format might be non-standard
- Use `parse=False` to get raw output
- Download more templates if platform is missing

## Platform Not Detected

**Symptom:** `session.platform` is None

**Debug:**
```python
session = api.connect("device")
print(session.platform)  # None

# Check show version output
result = api.send(session, "show version", parse=False)
print(result.raw_output[:500])
```

**Solution:**
Platform detection looks for keywords in show version:
- Cisco: "Cisco IOS Software"
- Arista: "Arista"
- Juniper: "JUNOS"

If not detected, parsing won't work. Set manually if needed (not currently supported, but you can modify the session object).

## Session Stuck

**Symptom:** Command hangs or times out

**Solutions:**
```python
# Increase timeout
result = api.send(session, "show tech-support", timeout=120)

# Check if session still active
session.is_connected()  # Returns 1 or 0

# Disconnect and reconnect
api.disconnect(session)
session = api.connect("device")
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
""")
        layout.addWidget(text)
        return widget

    def _copy_sample_code(self):
        """Copy sample code to clipboard."""
        sample = """# nterm API Quick Start
from nterm.scripting import api

# Unlock vault
api.unlock("vault-password")

# List devices
devices = api.devices()

# Connect to device
session = api.connect("device-name")

# Execute command
result = api.send(session, "show version")

# Access parsed data
if result.parsed_data:
    print(result.parsed_data[0])
else:
    print(result.raw_output)

# Disconnect
api.disconnect(session)
"""
        from PyQt6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(sample)

        QMessageBox.information(
            self,
            "Copied",
            "Sample code copied to clipboard!\n\nPaste into IPython to get started."
        )