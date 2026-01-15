#!/usr/bin/env python3
"""
backup_configs.py - Network Device Configuration Backup

Usage in nterm IPython:
    %load sample_scripts/backup_configs.py
    # Execute cell (Shift+Enter), then:
    backup_configs(api, folder="Lab-WAN", backup_dir="configs")

This script connects to network devices and saves their running configurations
to timestamped files. Platform-specific commands are used automatically.
"""

import os
from datetime import datetime
from pathlib import Path

# Platform-specific configuration commands
CONFIG_COMMANDS = {
    'cisco_ios': 'show running-config',
    'cisco_iosxe': 'show running-config',
    'cisco_nxos': 'show running-config',
    'cisco_iosxr': 'show running-config',
    'arista_eos': 'show running-config',
    'juniper_junos': 'show configuration',
}

DEFAULT_CONFIG_COMMAND = 'show running-config'


def get_config_command(platform):
    """Get the appropriate config command for platform."""
    if not platform:
        return DEFAULT_CONFIG_COMMAND
    return CONFIG_COMMANDS.get(platform, DEFAULT_CONFIG_COMMAND)


def sanitize_filename(name):
    """Make device name safe for filesystem."""
    return "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in name)


def backup_device(api, session, device_name, backup_dir):
    """
    Backup configuration for a single device.
    
    Returns: (success: bool, message: str, filepath: str)
    """
    try:
        # Get platform-specific config command
        platform = session.platform or 'unknown'
        cmd = get_config_command(platform)
        
        # Execute command (parse=False to get raw config text)
        print(f"  Fetching config with: {cmd}")
        result = api.send(session, cmd, parse=False, timeout=120)
        
        if not result.raw_output:
            return False, "No output received", None
        
        # Create filename: devicename_YYYYMMDD_HHMMSS.cfg
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = sanitize_filename(device_name)
        filename = f"{safe_name}_{timestamp}.cfg"
        filepath = backup_dir / filename
        
        # Write config to file
        filepath.write_text(result.raw_output, encoding='utf-8')
        
        # Get file size for reporting
        size_kb = filepath.stat().st_size / 1024
        
        return True, f"Saved {size_kb:.1f} KB", str(filepath)
        
    except Exception as e:
        return False, f"Error: {str(e)}", None


def backup_configs(api, folder=None, backup_dir="config_backups", vault_password=None):
    """
    Backup configurations from network devices.
    
    Args:
        api: NTermAPI instance
        folder: Target folder name (None = all devices)
        backup_dir: Output directory for backup files
        vault_password: Vault password (None = must be unlocked already)
    
    Returns:
        dict: Results with 'success' and 'failed' lists
    """
    print("\n" + "="*70)
    print("Network Device Configuration Backup")
    print("="*70 + "\n")
    
    # Unlock vault if needed
    if not api.vault_unlocked:
        if vault_password:
            print("Unlocking vault...")
            api.unlock(vault_password)
        else:
            print("ERROR: Vault is locked. Pass vault_password parameter or unlock manually:")
            print("  api.unlock('your-password')")
            return {'success': [], 'failed': []}
    
    # Get target devices
    if folder:
        print(f"Target folder: {folder}")
        devices = api.devices(folder=folder)
    else:
        print("Target: All devices")
        devices = api.devices()
    
    if not devices:
        print("No devices found.")
        return {'success': [], 'failed': []}
    
    print(f"Found {len(devices)} device(s)\n")
    
    # Create backup directory
    backup_path = Path(backup_dir)
    backup_path.mkdir(exist_ok=True)
    print(f"Backup directory: {backup_path.absolute()}\n")
    
    # Backup each device
    results = {
        'success': [],
        'failed': [],
    }
    
    for i, device in enumerate(devices, 1):
        print(f"[{i}/{len(devices)}] {device.name} ({device.hostname})")
        
        session = None
        try:
            # Connect to device
            print(f"  Connecting...")
            session = api.connect(device.name)
            
            if not session.is_connected():
                results['failed'].append((device.name, "Connection failed"))
                print(f"  ❌ Connection failed\n")
                continue
            
            platform = session.platform or 'unknown'
            print(f"  Platform: {platform}")
            
            # Backup configuration
            success, message, filepath = backup_device(api, session, device.name, backup_path)
            
            if success:
                results['success'].append(device.name)
                print(f"  ✓ {message}")
                print(f"  → {filepath}\n")
            else:
                results['failed'].append((device.name, message))
                print(f"  ❌ {message}\n")
                
        except Exception as e:
            results['failed'].append((device.name, str(e)))
            print(f"  ❌ Error: {e}\n")
            
        finally:
            # Always disconnect
            if session and session.is_connected():
                try:
                    api.disconnect(session)
                except:
                    pass
    
    # Print summary
    print("\n" + "="*70)
    print("Backup Summary")
    print("="*70)
    print(f"\nSuccessful: {len(results['success'])}")
    for name in results['success']:
        print(f"  ✓ {name}")
    
    if results['failed']:
        print(f"\nFailed: {len(results['failed'])}")
        for name, error in results['failed']:
            print(f"  ❌ {name}: {error}")
    
    print(f"\nBackup files saved to: {backup_path.absolute()}")
    print("\n" + "="*70 + "\n")
    
    return results
