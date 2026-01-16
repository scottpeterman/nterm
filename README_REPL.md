# nterm REPL - Safe Network Automation Interface

A secure, policy-controlled command-line interface for network devices that bridges human exploration and programmatic automation. The same interface works for interactive terminal sessions and MCP-driven agents.

## Why This Exists

Traditional network automation forces you to choose between:
- **SSH terminals** - Interactive but unstructured, prone to errors
- **NETCONF/APIs** - Programmatic but not explorable
- **Ansible/Salt** - Batch automation, not real-time interaction
- **Vendor CLIs** - Raw text, manual parsing, no guardrails

**nterm REPL eliminates these tradeoffs:**
- 🔒 **Secure** - Policy-based command filtering, credential vault
- 📊 **Structured** - TextFSM parsing with multiple output formats
- 🎯 **Interactive** - Natural command execution with visual feedback
- 🤖 **Programmatic** - JSON output for MCP agents and automation
- 🛡️ **Safe** - Read-only mode, command deny-lists, session isolation
- ⚡ **Quick Commands** - Platform-aware shortcuts for common tasks

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Commands Reference](#commands-reference)
- [Quick Commands](#quick-commands-new)
- [Output Modes & Formats](#output-modes--formats)
- [Security & Policies](#security--policies)
- [Use Cases](#use-cases)
- [Programmatic Usage](#programmatic-usage)
- [Troubleshooting](#troubleshooting)
- [Examples](#examples)
- [Architecture](#architecture)

## Installation

### Requirements
```bash
# Core requirements
Python 3.10+
nterm library

# Optional for enhanced display
pip install rich
```

### Setup
```python
from nterm.scripting import api

# Verify installation
api.db_info()
```

## Quick Start

### Launch the REPL
```python
from nterm.scripting import api

# Start interactive REPL
api.repl()
```

### Basic Workflow
```
============================================================
nterm REPL - Safe Network Automation Interface
============================================================

Policy: read_only
Output: parsed (text)
Vault: locked

Type :help for commands, :exit to quit

nterm> :unlock
Enter vault password: ********
✓ Vault unlocked

nterm> :devices
Name                      Hostname             Port   Folder         
------------------------------------------------------------------
usa-leaf-1                172.16.10.21         22     Lab-USA
usa-spine-1               172.16.10.2          22     Lab-USA
eng-leaf-1                172.16.2.21          22     Lab-ENG

3 device(s)

nterm> :connect usa-leaf-1
✓ Connected to usa-leaf-1 (172.16.10.21:22)
  Platform: cisco_ios
  Prompt: usa-leaf-1#

📊 usa-leaf-1> :version
──────────────────────────────────────────────────
  Version:  15.2(4.0.55)E
  Hardware: IOSv
  Serial:   9J0PD0QB9W1
  Uptime:   1 week, 4 days, 7 minutes
──────────────────────────────────────────────────
[0.502s]

📊 usa-leaf-1> :interfaces
[Parsed: cisco_ios | interfaces_status | format: rich]
------------------------------------------------------------
┌─────────┬──────────────────┬────────┬───────────┬─────────┐
│ FC_MODE │ NAME             │ PORT   │ STATUS    │ VLAN_ID │
├─────────┼──────────────────┼────────┼───────────┼─────────┤
│         │ To usa-spine-2   │ Gi0/0  │ connected │ trunk   │
│         │ To usa-spine-1   │ Gi0/1  │ connected │ trunk   │
│         │ Server Port 1    │ Gi0/2  │ notconnect│ 110     │
└─────────┴──────────────────┴────────┴───────────┴─────────┘
[0.505s]

📊 usa-leaf-1> :neighbors
Local Interface      Neighbor                       Remote Port          Platform
------------------------------------------------------------------------------------------
Gi0/0                usa-spine-2.lab.local          Ethernet1            Arista vEOS
Gi0/1                usa-spine-1.lab.local          Ethernet1            Arista vEOS

2 neighbor(s)
[0.456s]
```

## Commands Reference

### Vault Commands
```
:unlock              Unlock credential vault (secure password prompt)
:lock                Lock credential vault
```

### Inventory Commands
```
:creds [pattern]     List available credentials (supports glob patterns)
:devices [pattern]   List available devices [--folder name]
:folders             List all folders
```

### Session Commands
```
:connect <device>    Connect to device [--cred name] [--debug]
:disconnect          Close current connection
:sessions            List all active sessions (shows current with →)
```

### Quick Commands (NEW - Platform-Aware)
```
:config              Fetch running configuration
:version             Fetch and display version info (structured)
:interfaces          Fetch interface status
:neighbors           Fetch CDP/LLDP neighbors (tries both automatically)
:bgp                 Fetch BGP summary
:routes              Fetch routing table
:intf <name>         Fetch specific interface details
```

### Output Control
```
:mode [raw|parsed]   Control parsing behavior
:format [text|rich|json]   Display format (parsed mode only)
:set_hint <platform>   Override platform detection
:clear_hint          Use auto-detected platform
```

### Debugging & Info
```
:debug [on|off]      Show full result dictionaries
:dbinfo              Check TextFSM database health
:policy [read_only|ops]   Set command filtering policy
:help                Show all commands
:exit                Disconnect all and exit
```

### Raw Command Execution
Any input that doesn't start with `:` is sent to the connected device as a CLI command.

## Quick Commands (NEW)

Quick commands are **platform-aware shortcuts** that automatically use the correct syntax for the detected platform. No more remembering `show run` vs `show configuration`.

### :version
Fetches and displays structured version information:

```
📊 usa-leaf-1> :version
──────────────────────────────────────────────────
  Version:  15.2(4.0.55)E
  Hardware: IOSv
  Serial:   9J0PD0QB9W1
  Uptime:   1 week, 4 days, 7 minutes
──────────────────────────────────────────────────
[0.502s]
```

### :config
Fetches running configuration (uses correct command per platform):

| Platform | Command Used |
|----------|--------------|
| cisco_ios | `show running-config` |
| arista_eos | `show running-config` |
| juniper_junos | `show configuration` |

### :interfaces
Fetches interface status table:

```
📊 device> :interfaces
[Parsed: cisco_ios | interfaces_status | format: rich]
┌──────────────┬────────┬───────────┬─────────┐
│ NAME         │ PORT   │ STATUS    │ VLAN_ID │
├──────────────┼────────┼───────────┼─────────┤
│ Uplink       │ Gi0/0  │ connected │ trunk   │
│ Server Port  │ Gi0/1  │ notconnect│ 100     │
└──────────────┴────────┴───────────┴─────────┘
```

### :neighbors
Automatically tries CDP then LLDP (or LLDP first for non-Cisco):

```
📊 usa-leaf-1> :neighbors
Local Interface      Neighbor                       Remote Port          Platform
------------------------------------------------------------------------------------------
Gi0/0                usa-spine-2.lab.local          Ethernet1            Arista vEOS
Gi0/1                usa-spine-1.lab.local          Ethernet1            Arista vEOS

2 neighbor(s)
[0.456s]
```

### :bgp
Fetches BGP summary:

```
📊 spine-1> :bgp
[Parsed: arista_eos | bgp_summary | format: text]
NEIGHBOR       | AS     | STATE_PFXRCD
10.0.0.1       | 65001  | 12
10.0.0.2       | 65002  | 8
```

### :routes
Fetches routing table:

```
📊 device> :routes
[Parsed: cisco_ios | routing_table | format: text]
PROTOCOL | NETWORK        | NEXT_HOP     | INTERFACE
C        | 10.0.0.0/24    | directly     | Gi0/0
O        | 192.168.1.0/24 | 10.0.0.1     | Gi0/1
```

### :intf <name>
Fetches specific interface details:

```
📊 device> :intf Gi0/1
[Parsed: cisco_ios | interface_detail | format: text]
INTERFACE     | IP_ADDRESS   | STATUS | MTU  | BANDWIDTH
Gi0/1         | 10.0.0.1     | up     | 1500 | 1000000
```

## Output Modes & Formats

### Output Modes

#### Parsed Mode (Default)
Commands are parsed into structured data using TextFSM templates.

```
📊 wan-core-1> show cdp neighbors

[Parsed with cisco_ios - format: text]
------------------------------------------------------------
NEIGHBOR_NAME          | LOCAL_INTERFACE | PLATFORM
usa-rtr-1.lab.local    | Eth 1/1         | Gig
eng-rtr-1.lab.local    | Eth 1/2         | Gig
```

**Benefits:**
- Structured data extraction
- Multiple output formats available
- Consistent data model across devices

#### Raw Mode
Returns plain text output from the device.

```
📄 wan-core-1> show version
Cisco IOS Software, 7200 Software (C7200-ADVENTERPRISEK9-M)...
[Raw device output]
```

**Use when:**
- Command has no TextFSM template
- Need exact device output
- Debugging platform detection issues

### Output Formats (Parsed Mode Only)

#### Text Format (Default)
Clean ASCII tables, works everywhere.

```
📊 device> :format text
Output format: text

📊 device> show ip interface brief
interface         | IP_ADDRESS   | STATUS    | PROTO
Ethernet1/0       | 172.16.1.2   | up        | up
```

#### Rich Format
Beautiful colored tables using the Rich library.

```
📊 device> :format rich
Output format: rich

📊 device> show ip interface brief
┏━━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━┓
┃ interface   ┃ IP_ADDRESS   ┃ STATUS ┃ PROTO ┃
┡━━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━┩
│ Ethernet1/0 │ 172.16.1.2   │ up     │ up    │
└─────────────┴──────────────┴────────┴───────┘
```

**Requires:** `pip install rich`  
**Falls back** to text format if Rich not available

#### JSON Format
Raw structured data, perfect for programmatic use.

```
📊 device> :format json
Output format: json

📊 device> show ip interface brief
[
  {
    "interface": "Ethernet1/0",
    "IP_ADDRESS": "172.16.1.2",
    "STATUS": "up",
    "PROTO": "up"
  }
]
```

**Use for:**
- MCP agent integration
- Data export and processing
- Scripting and automation
- API-style interactions

## Security & Policies

### Read-Only Mode (Default)
Blocks configuration-changing commands.

**Blocked commands include:**
```
conf t, configure, write, reload, shutdown
copy, delete, format, commit, install
set, unset, clear (depending on platform)
```

**Example:**
```
📊 device> conf t
Error: Blocked by policy (read_only): conf t
```

### Operations Mode
Allows configuration changes (use with caution).

```
nterm> :policy ops
Policy mode: ⚡ ops

# Now configuration commands are allowed
```

### Custom Policies
```python
from nterm.scripting.repl import REPLPolicy

# Custom deny list
policy = REPLPolicy(
    mode="read_only",
    deny_substrings=["reload", "terminal monitor"],
    max_output_chars=500000,
    max_command_seconds=120
)

api.repl(policy=policy)
```

### Allow-List Mode
Restrict to specific command prefixes only:

```python
policy = REPLPolicy(
    mode="read_only",
    allow_prefixes=["show", "display", "get"],  # Only these allowed
)
```

### Credential Security
- Passwords never displayed in terminal
- Secure `getpass` prompt for vault unlock
- Encrypted credential storage
- Session-based authentication

## Use Cases

### 1. Interactive Network Exploration (Humans)

**Quick device checks with structured output:**
```
nterm> :unlock
nterm> :connect usa-spine-1

📊 usa-spine-1> :version
──────────────────────────────────────────────────
  Version:  4.28.1F
  Hardware: DCS-7050SX3-48YC8
  Serial:   SSJ12345678
  Uptime:   45 days, 12:34:56
──────────────────────────────────────────────────

📊 usa-spine-1> :neighbors
[Quick topology view]

📊 usa-spine-1> :bgp
[BGP health at a glance]
```

**Rich format for pattern recognition:**
```
📊 device> :format rich
📊 device> :interfaces
[Beautiful colored table helps spot patterns quickly]
```

### 2. Data Export and Analysis

**Export to JSON for processing:**
```
📊 device> :format json
📊 device> show ip route
[Copy JSON output]
```

**Process with external tools:**
```bash
# Process with jq
cat routes.json | jq '.[] | select(.PROTOCOL=="O")'
```

### 3. MCP Agent Integration

**Agent can use same commands:**
```python
result = repl.handle_line(":connect wan-core-1")
result = repl.handle_line(":version")  # Structured version info
result = repl.handle_line(":neighbors")  # CDP/LLDP auto-detection

# Access structured data
version_info = result["data"]["result"]["version_info"]
```

### 4. Multi-Device Quick Checks

```
nterm> :connect usa-leaf-1
📊 usa-leaf-1> :version
[Quick check]
📊 usa-leaf-1> :disconnect

nterm> :connect usa-leaf-2
📊 usa-leaf-2> :version
[Quick check]
```

## Programmatic Usage

### Basic Pattern

```python
from nterm.scripting.repl import NTermREPL
from nterm.scripting import api

repl = NTermREPL(api=api)

# Unlock and connect
repl.do_unlock("vault-password")  # Direct unlock
result = repl.handle_line(":connect wan-core-1")

# Use quick commands
result = repl.handle_line(":version")
version_info = result["data"]["result"]["version_info"]
print(f"Version: {version_info['version']}")

# Use raw commands
result = repl.handle_line("show ip interface brief")
interfaces = result["data"]["result"]["parsed_data"]

# Cleanup
repl.handle_line(":disconnect")
```

### Result Structure

All commands return a dictionary with this structure:

```python
{
    "ok": bool,           # Success/failure
    "data": {             # Present if ok=True
        "type": str,      # Command type
        # Type-specific fields
    },
    "error": str,         # Present if ok=False
    "ts": str            # ISO timestamp
}
```

**Quick command result example (:version):**
```python
{
    "ok": True,
    "data": {
        "type": "version",
        "result": {
            "parsed_data": [...],
            "parse_success": True,
            "platform": "cisco_ios",
            "raw_output": "...",
            "elapsed_seconds": 0.502,
            "command_type": "version",
            "version_info": {
                "version": "15.2(4.0.55)E",
                "hardware": "IOSv",
                "serial": "9J0PD0QB9W1",
                "uptime": "1 week, 4 days, 7 minutes"
            }
        }
    },
    "ts": "2026-01-15T10:30:00"
}
```

**Neighbors result example:**
```python
{
    "ok": True,
    "data": {
        "type": "neighbors",
        "result": {
            "parsed_data": [...],
            "neighbor_info": [
                {
                    "local_interface": "Gi0/0",
                    "neighbor_device": "usa-spine-2.lab.local",
                    "neighbor_interface": "Ethernet1",
                    "platform": "Arista vEOS"
                },
                ...
            ],
            "elapsed_seconds": 0.456
        }
    }
}
```

### Custom Policy Example

```python
from nterm.scripting.repl import REPLPolicy

# Strict read-only policy
strict_policy = REPLPolicy(
    mode="read_only",
    deny_substrings=[
        "reload",
        "write",
        "copy",
        "terminal monitor"
    ],
    allow_prefixes=[
        "show",
        "display",
        "get"
    ],
    max_output_chars=100000,
    max_command_seconds=30
)

repl = NTermREPL(api=api, policy=strict_policy)
```

## Troubleshooting

### Parsing Not Working

**Symptom:** Raw text output when expecting parsed tables

**Solution:**
```
📊 device> :dbinfo

# If database is empty or missing:
⚠️  WARNING: Database file is empty (0 bytes)!
```

**Fix:** Download templates via **Dev → Download NTC Templates...**

### Wrong Platform Detected

**Symptom:** Parsing fails or returns incorrect data

**Solution:**
```
📊 device> :debug on
📊 device> show version

[DEBUG shows: "platform": "cisco_ios"]

# If wrong platform:
📊 device> :set_hint arista_eos
📊 device[arista_eos]> show version
[Now uses correct parser]
```

### Command Blocked by Policy

**Symptom:** `Error: Blocked by policy`

**Solution:**
```
# Check current policy
nterm> :policy
Policy mode: 🔒 read_only

# Switch to ops mode (if needed and authorized)
nterm> :policy ops
Policy mode: ⚡ ops
```

### Quick Command Not Available

**Symptom:** `Error: Command 'X' not available for platform 'Y'`

**Cause:** Platform doesn't support that command type (e.g., CDP on Arista)

**Solution:** Use the raw command directly or try alternative:
```
# Instead of :neighbors (which might try CDP first)
📊 device> show lldp neighbors detail
```

### Connection Issues

**Symptom:** Unable to connect to device

**Check:**
```
nterm> :devices
# Verify device exists and hostname is correct

nterm> :creds
# Verify credentials are available

# Try explicit credential
nterm> :connect device --cred specific_cred

# Enable debug mode
nterm> :connect device --debug
```

### Rich Format Not Working

**Symptom:** Falls back to text format

**Fix:**
```bash
pip install rich
```

## Examples

### Example 1: Quick Health Check Across Devices

```
nterm> :unlock
nterm> :format rich

nterm> :connect usa-spine-1
📊 usa-spine-1> :version
📊 usa-spine-1> :bgp
📊 usa-spine-1> :disconnect

nterm> :connect usa-spine-2
📊 usa-spine-2> :version
📊 usa-spine-2> :bgp
📊 usa-spine-2> :disconnect
```

### Example 2: Topology Discovery

```
nterm> :connect core-router
📊 core-router> :neighbors
[See all directly connected devices]

📊 core-router> :routes
[See routing table]

📊 core-router> :bgp
[See BGP peering status]
```

### Example 3: Programmatic Multi-Device Audit

```python
from nterm.scripting.repl import NTermREPL
from nterm.scripting import api

repl = NTermREPL(api=api)
repl.do_unlock("password")

devices = ["spine-1", "spine-2", "leaf-1", "leaf-2"]
audit_results = {}

for device in devices:
    result = repl.handle_line(f":connect {device}")
    if not result["ok"]:
        audit_results[device] = {"error": result["error"]}
        continue
    
    # Get version info
    ver_result = repl.handle_line(":version")
    version_info = ver_result["data"]["result"]["version_info"]
    
    # Get neighbor count
    nbr_result = repl.handle_line(":neighbors")
    neighbor_info = nbr_result["data"]["result"].get("neighbor_info", [])
    
    audit_results[device] = {
        "version": version_info["version"],
        "hardware": version_info["hardware"],
        "uptime": version_info["uptime"],
        "neighbor_count": len(neighbor_info),
    }
    
    repl.handle_line(":disconnect")

# Print audit report
import json
print(json.dumps(audit_results, indent=2))
```

### Example 4: Export Interface Data to JSON

```
nterm> :connect distribution-1
📊 distribution-1> :format json
📊 distribution-1> :interfaces

# Copy JSON output, save to file, process with jq:
# cat interfaces.json | jq '.[] | select(.STATUS=="notconnect")'
```

## Architecture

### Components

```
┌─────────────────────────────────────────────────┐
│                   User/Agent                    │
└───────────────────┬─────────────────────────────┘
                    │ :commands / raw CLI
                    ▼
┌─────────────────────────────────────────────────┐
│              NTermREPL                          │
│  ┌──────────────────────────────────────────┐  │
│  │  Command Router & State Manager          │  │
│  │  - Parse :commands                        │  │
│  │  - Quick commands → platform_utils        │  │
│  │  - Apply policy                           │  │
│  │  - Manage session                         │  │
│  └──────────────────────────────────────────┘  │
└───────────────────┬─────────────────────────────┘
                    │ API calls
                    ▼
┌─────────────────────────────────────────────────┐
│               NTermAPI                          │
│  ┌──────────────────────────────────────────┐  │
│  │  Platform-Aware Execution                 │  │
│  │  - send_platform_command()               │  │
│  │  - send_first() for fallbacks            │  │
│  │  - extract_version_info()                │  │
│  │  - extract_neighbor_info()               │  │
│  └──────────────────────────────────────────┘  │
└───────────────────┬─────────────────────────────┘
                    │ SSH
                    ▼
┌─────────────────────────────────────────────────┐
│            Network Devices                      │
└─────────────────────────────────────────────────┘
```

### State Flow

```
REPLState:
  ├─ policy: REPLPolicy
  │    ├─ mode: "read_only" | "ops"
  │    ├─ deny_substrings: List[str]
  │    ├─ allow_prefixes: List[str]
  │    └─ resource_limits: max_output, max_timeout
  │
  ├─ output_mode: "raw" | "parsed"
  ├─ output_format: "text" | "rich" | "json"
  ├─ platform_hint: Optional[str]
  ├─ debug_mode: bool
  ├─ vault_unlocked: bool
  └─ session: Optional[ActiveSession]
       ├─ device_name: str
       ├─ platform: str
       ├─ prompt: str
       └─ is_connected: bool
```

### Design Principles

1. **Single Interface, Multiple Uses**
   - Same commands for humans and agents
   - Output format adapts to use case
   - Consistent behavior across contexts

2. **Platform Awareness**
   - Quick commands auto-select correct syntax
   - CDP/LLDP fallback handled automatically
   - Version/neighbor info normalized across vendors

3. **Security First**
   - Policy enforcement at REPL layer
   - Credential vault with secure unlock
   - Command filtering and validation
   - Session isolation

4. **Observable Actions**
   - All commands visible
   - Debug mode for troubleshooting
   - Timestamped results
   - Clear error messages

5. **Graceful Degradation**
   - Rich → text fallback
   - Parsed → raw fallback
   - Clear error handling
   - Informative health checks