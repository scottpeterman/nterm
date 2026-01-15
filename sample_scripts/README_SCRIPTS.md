# nterm API Example Scripts

Collection of ready-to-run automation scripts for the nterm API.

## Usage

1. Open nterm IPython console: **Dev → IPython → Open in Tab**
2. Load a script: `%load sample_scripts/backup_configs.py`
3. Execute the cell (Shift+Enter) to load the function definitions
4. Call the function: `backup_configs(api)`

The scripts define functions that take `api` as a parameter, so you explicitly pass in the API instance. This makes the code clearer and easier to test.

---

## Available Scripts

### read_env.py

Display API environment and database information.

```python
%load sample_scripts/read_env.py
# Execute cell, then:
read_env(api)
```

### backup_configs.py

Backs up device configurations to timestamped files. Automatically uses the correct command for each platform (Cisco, Arista, Juniper).

```python
%load sample_scripts/backup_configs.py
# Execute cell, then:
backup_configs(api)
backup_configs(api, folder="Production")
backup_configs(api, backup_dir="my_backups")
```

**Output:**
```
config_backups/
├── wan-core-1_20250115_143022.cfg
├── eng-spine-1_20250115_143045.cfg
└── usa-leaf-1_20250115_143108.cfg
```

---

### version_audit.py

Collects software versions from all devices and generates a CSV report. Useful for compliance audits and upgrade planning.

```python
%load sample_scripts/version_audit.py
# Execute cell, then:
version_audit(api)
version_audit(api, folder="Core-Switches")
```

**Output:** `version_audit_20250115_143530.csv`

Contains: device name, hostname, platform, software version, hardware model, serial number, uptime

---

### interface_errors.py

Scans all interfaces for errors and down/down status.

```python
%load sample_scripts/interface_errors.py
# Execute cell, then:
interface_errors(api)
interface_errors(api, folder="Production", error_threshold=100)
```

Reports interfaces with input/output errors, CRC errors, or down/down status.

---

### neighbor_discovery.py

Collects CDP/LLDP neighbor information to display network topology.

```python
%load sample_scripts/neighbor_discovery.py
# Execute cell, then:
neighbor_discovery(api)
neighbor_discovery(api, folder="Core")
```

Shows which devices are connected to each other and on which interfaces.

---

## Creating Your Own Scripts

The pattern is simple - define a function that takes `api` as the first parameter:

```python
"""
my_script.py - Brief description

Usage:
    %load sample_scripts/my_script.py
    my_function(api)
"""

def my_function(api, folder=None, output_file="results.txt"):
    """
    Do something useful.
    
    Args:
        api: NTermAPI instance
        folder: Target folder (optional)
        output_file: Where to save results
    
    Returns:
        Results data structure
    """
    # Unlock vault if needed
    if not api.vault_unlocked:
        print("ERROR: Vault is locked")
        return
    
    # Get devices
    devices = api.devices(folder=folder)
    
    # Do your work
    for device in devices:
        session = api.connect(device.name)
        result = api.send(session, "show version")
        
        # Process result.parsed_data or result.raw_output
        
        api.disconnect(session)
    
    return results
```

Then load and run it:
```python
%load sample_scripts/my_script.py
# Execute cell (Shift+Enter), then:
results = my_function(api, folder="Lab")
```

---

## Common Patterns

### Target Specific Devices

```python
# Single folder
devices = api.devices(folder="Lab-WAN")

# Glob pattern
devices = api.devices("spine-*")

# Search query
devices = api.search("cisco")

# All devices
devices = api.devices()
```

### Unlock Vault

```python
# Check if unlocked
if not api.vault_unlocked:
    api.unlock("your-password")

# Or pass as parameter to your function
def my_function(api, vault_password=None):
    if not api.vault_unlocked and vault_password:
        api.unlock(vault_password)
```

### Get Parsed Data

```python
result = api.send(session, "show interfaces status")

if result.parsed_data:
    for intf in result.parsed_data:
        print(f"{intf['interface']}: {intf['status']}")
```

### Get Raw Output

```python
# For configs or unparsed commands
result = api.send(session, "show running-config", parse=False)
config_text = result.raw_output
```

### Platform Detection

```python
session = api.connect("device")
platform = session.platform  # 'cisco_ios', 'arista_eos', etc.

# Use platform-specific commands
if platform == 'juniper_junos':
    cmd = "show configuration"
else:
    cmd = "show running-config"
```

### Error Handling

```python
for device in devices:
    session = None
    try:
        session = api.connect(device.name)
        result = api.send(session, command)
        # Process result
    except Exception as e:
        print(f"Failed on {device.name}: {e}")
    finally:
        if session and session.is_connected():
            api.disconnect(session)
```

---

## Why This Pattern?

The `%load` + function call pattern has several advantages:

1. **Visible**: You see the code before executing it
2. **Explicit**: You see exactly what parameters you're passing
3. **Testable**: Functions can be imported and tested independently
4. **Reusable**: Same function can be called multiple times with different parameters
5. **Clear**: No magic globals or hidden state

Compare:
```python
# Old auto-execute pattern
%run backup_configs.py  # Must edit FOLDER_NAME in file

# New function pattern
%load backup_configs.py
# Execute cell (Shift+Enter), then:
backup_configs(api, folder="Production")  # Clear and flexible
```

**Note:** You can also use `%run` if you prefer not to see the code:
```python
%run sample_scripts/backup_configs.py
backup_configs(api, folder="Production")
```

---

## Script Ideas

Here are some ideas for scripts you might want to create:

- **interface_audit.py** - Find interfaces with errors or down/down status
- **cdp_map.py** - Build network topology from CDP/LLDP neighbors
- **vlan_audit.py** - List all VLANs across switches
- **config_diff.py** - Compare configs against baseline or previous backup
- **acl_search.py** - Search for specific ACL entries across devices
- **mac_address_search.py** - Find which switch port a MAC address is on
- **bgp_neighbors.py** - Collect BGP neighbor status from all routers
- **ospf_audit.py** - Check OSPF neighbor states and interface costs
- **port_security.py** - Audit port security configuration and violations
- **stp_audit.py** - Check spanning tree topology and root bridges
- **firmware_check.py** - Compare running versions against target versions
- **change_validation.py** - Run post-change validation commands
- **bulk_config.py** - Push configuration snippets to multiple devices

---

## Tips

### Development Workflow

1. Prototype in IPython interactively
2. Once working, paste into a .py file
3. Test with `%run`
4. Iterate

### Debugging

```python
# Check what's available
api.status()        # API summary
api.db_info()       # TextFSM database info
api.help()          # Command reference

# Debug parsing failures
result = api.send(session, "show version")
if not result.parsed_data:
    debug = api.debug_parse("show version", result.raw_output, session.platform)
    print(debug)
```

### Performance

- Reuse sessions when running multiple commands on same device
- Use `parse=False` when you don't need structured data (faster)
- Set longer timeouts for slow commands: `api.send(session, cmd, timeout=300)`

---

## Requirements

- nterm with scripting support: `pip install ntermqt[scripting]`
- TextFSM template database (download via **Dev → Download NTC Templates...**)
- Unlocked credential vault

---

## Contributing

Got a useful script? Share it! These examples are meant to show the API in action and give people a starting point for their own automation.
