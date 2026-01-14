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

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Commands Reference](#commands-reference)
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
Python 3.8+
nterm library

# Optional for enhanced display
pip install rich
```

### Setup
```python
from nterm.scripting import api

# Download TextFSM templates (first time only)
api.download_templates()

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
Vault unlocked

nterm> :devices
Name                 Hostname             Folder         
-------------------------------------------------------
wan-core-1           172.16.128.1         Lab-WAN
eng-spine-1          172.16.2.2           Lab-ENG

nterm> :connect wan-core-1
Connected to wan-core-1 (172.16.128.1:22)
Platform: cisco_ios
Prompt: wan-core-1#

📊 wan-core-1> show ip interface brief
[Parsed with cisco_ios - format: text]
------------------------------------------------------------
interface         | IP_ADDRESS   | STATUS    | PROTO
FastEthernet0/0   | unassigned   | admin dn  | down
Ethernet1/0       | 172.16.1.2   | up        | up
Ethernet1/1       | 172.16.100.1 | up        | up

[0.234s]
```

## Commands Reference

### Authentication & Security
```
:unlock              Unlock credential vault (secure password prompt)
:lock                Lock credential vault
:creds [pattern]     List available credentials
```

### Device Management
```
:devices [pattern]   List available devices (supports glob patterns)
:connect <device> [--cred name]   Connect to device
:disconnect          Close current connection
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
:exit                Exit REPL
```

### Command Execution
Any input that doesn't start with `:` is sent to the connected device as a CLI command.

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
Policy mode: ops

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

### Credential Security
- Passwords never displayed in terminal
- Secure `getpass` prompt for vault unlock
- Encrypted credential storage
- Session-based authentication

## Use Cases

### 1. Interactive Network Exploration (Humans)

**Visual device discovery:**
```
nterm> :devices Lab-*
Name                 Hostname             Folder         
-------------------------------------------------------
Lab-ENG-spine-1      172.16.2.2           Lab-ENG
Lab-USA-spine-1      172.16.10.2          Lab-USA
```

**Rich format for pattern recognition:**
```
📊 device> :format rich
📊 device> show interfaces status
[Beautiful colored table helps spot patterns quickly]
```

**Quick multi-device checks:**
```
📊 usa-spine-1> show version | include uptime
📊 usa-spine-1> :disconnect

nterm> :connect eng-spine-1
📊 eng-spine-1> show version | include uptime
```

### 2. Data Export and Analysis

**Export to JSON for processing:**
```
📊 device> :format json
📊 device> show ip route
[Copy JSON output]
📊 device> show interfaces
[Copy JSON output]

# Process in jq, Python, or save to file
```

**Parse once, use everywhere:**
```bash
# Export from REPL
$ nterm-export > interfaces.json

# Process with jq
$ cat interfaces.json | jq '.[] | select(.STATUS=="up")'

# Load in Python
import json
interfaces = json.load(open("interfaces.json"))
```

### 3. MCP Agent Integration

**Agent workflow:**
```python
from nterm.scripting.repl import NTermREPL
from nterm.scripting import api

# Initialize REPL for agent
repl = NTermREPL(api=api)

# Agent unlocks vault (password from secure store)
repl.handle_line(":unlock")  # Password via secure method

# Agent configures output
repl.handle_line(":format json")
repl.handle_line(":connect wan-core-1")

# Agent gathers data
version_result = repl.handle_line("show version")
if version_result["ok"]:
    version = version_result["data"]["result"]["parsed_data"]
    
# Agent analyzes
interface_result = repl.handle_line("show ip interface brief")
interfaces = interface_result["data"]["result"]["parsed_data"]

up_count = len([i for i in interfaces if i["STATUS"] == "up"])

# Agent takes action based on findings
if up_count < threshold:
    # Alert or remediate
    pass

# Cleanup
repl.handle_line(":disconnect")
```

**Benefits for agents:**
- Structured data (no text parsing)
- Same safety as humans
- Observable actions
- Consistent interface

### 4. Troubleshooting and Debugging

**Database health check:**
```
nterm> :dbinfo

TextFSM Database Info:
============================================================
Engine Available:  True
Database Size:     319,488 bytes (0.3 MB)

✓ Database appears healthy
```

**Debug mode for parsing issues:**
```
📊 device> :debug on
📊 device> show version

[DEBUG - Full Result Dict]
------------------------------------------------------------
{
  "parsed_data": [...],
  "parse_success": true,
  "platform": "cisco_ios"
}
------------------------------------------------------------
```

**Platform override for misbehaving devices:**
```
📊 device> :set_hint arista_eos
📊 device[arista_eos]> show version
[Uses Arista parser instead of auto-detected]
```

## Programmatic Usage

### Basic API Usage

```python
from nterm.scripting.repl import NTermREPL, REPLPolicy
from nterm.scripting import api

# Create REPL instance
repl = NTermREPL(api=api)

# Execute commands programmatically
result = repl.handle_line(":unlock")
result = repl.handle_line(":connect wan-core-1")
result = repl.handle_line(":format json")
result = repl.handle_line("show ip interface brief")

# Access structured result
if result["ok"]:
    data = result["data"]
    if data["type"] == "result":
        parsed_data = data["result"]["parsed_data"]
        # parsed_data is list[dict]
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

**Command result example:**
```python
{
    "ok": True,
    "data": {
        "type": "result",
        "result": {
            "parsed_data": [...],
            "parse_success": True,
            "platform": "cisco_ios",
            "raw_output": "...",
            "elapsed_seconds": 0.234
        }
    },
    "ts": "2025-01-14T10:30:00"
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

**Fix:**
```python
from nterm.scripting import api
api.download_templates()
```

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
Policy mode: read_only

# Switch to ops mode (if needed and authorized)
nterm> :policy ops
Policy mode: ops
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
```

### Rich Format Not Working

**Symptom:** Falls back to text format

**Fix:**
```bash
pip install rich
```

## Examples

### Example 1: Multi-Device Health Check

```python
from nterm.scripting.repl import NTermREPL
from nterm.scripting import api

repl = NTermREPL(api=api)
repl.handle_line(":unlock")  # Password from secure store
repl.handle_line(":format json")

devices = ["wan-core-1", "eng-spine-1", "usa-spine-1"]
health_report = {}

for device in devices:
    # Connect
    result = repl.handle_line(f":connect {device}")
    if not result["ok"]:
        health_report[device] = {"error": result["error"]}
        continue
    
    # Get version info
    version_result = repl.handle_line("show version")
    version_data = version_result["data"]["result"]["parsed_data"][0]
    
    # Get interface status
    intf_result = repl.handle_line("show ip interface brief")
    interfaces = intf_result["data"]["result"]["parsed_data"]
    
    # Calculate health metrics
    up_count = len([i for i in interfaces if i["STATUS"] == "up"])
    total_count = len(interfaces)
    
    health_report[device] = {
        "version": version_data.get("VERSION"),
        "uptime": version_data.get("UPTIME"),
        "interfaces_up": up_count,
        "interfaces_total": total_count,
        "health_percentage": (up_count / total_count) * 100
    }
    
    # Disconnect
    repl.handle_line(":disconnect")

# Process report
import json
print(json.dumps(health_report, indent=2))
```

### Example 2: Configuration Audit

```python
# Audit BGP configuration across devices
repl.handle_line(":format json")

devices = api.devices(pattern="*spine*")
bgp_configs = {}

for device in devices:
    repl.handle_line(f":connect {device.name}")
    
    # Get BGP summary
    result = repl.handle_line("show ip bgp summary")
    if result["ok"] and result["data"]["result"]["parsed_data"]:
        bgp_configs[device.name] = {
            "neighbors": result["data"]["result"]["parsed_data"]
        }
    
    repl.handle_line(":disconnect")

# Generate audit report
for device, config in bgp_configs.items():
    neighbor_count = len(config["neighbors"])
    print(f"{device}: {neighbor_count} BGP neighbors")
```

### Example 3: Interactive Exploration with Rich

```python
# Human-friendly interactive session
api.repl()
```

```
nterm> :unlock
nterm> :format rich
nterm> :connect eng-spine-1

📊 eng-spine-1> show interfaces status
[Beautiful Rich table with colors]

📊 eng-spine-1> show cdp neighbors
[Another formatted table]

📊 eng-spine-1> :set_hint cisco_ios
📊 eng-spine-1[cisco_ios]> show version
[Version info in structured format]
```

## Architecture

### Components

```
┌─────────────────────────────────────────────────┐
│                   User/Agent                    │
└───────────────────┬─────────────────────────────┘
                    │
                    │ Commands
                    ▼
┌─────────────────────────────────────────────────┐
│              NTermREPL                          │
│  ┌──────────────────────────────────────────┐  │
│  │  Command Router & State Manager          │  │
│  │  - Parse commands                         │  │
│  │  - Apply policy                           │  │
│  │  - Manage session                         │  │
│  └──────────────────────────────────────────┘  │
└───────────────────┬─────────────────────────────┘
                    │
                    │ API calls
                    ▼
┌─────────────────────────────────────────────────┐
│               NTermAPI                          │
│  ┌──────────────────────────────────────────┐  │
│  │  Device Management                        │  │
│  │  - Connection handling                    │  │
│  │  - Command execution                      │  │
│  │  - Credential management                  │  │
│  └──────────────────────────────────────────┘  │
└───────────────────┬─────────────────────────────┘
                    │
                    │ SSH/NETCONF
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
       ├─ client: SSHClient
       └─ is_connected: bool
```

### Design Principles

1. **Single Interface, Multiple Uses**
   - Same commands for humans and agents
   - Output format adapts to use case
   - Consistent behavior across contexts

2. **Security First**
   - Policy enforcement at REPL layer
   - Credential vault with secure unlock
   - Command filtering and validation
   - Session isolation

3. **Observable Actions**
   - All commands visible
   - Debug mode for troubleshooting
   - Timestamped results
   - Clear error messages

4. **Graceful Degradation**
   - Rich → text fallback
   - Parsed → raw fallback
   - Clear error handling
   - Informative health checks


