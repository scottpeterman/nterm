"""
version_audit.py - Software Version Audit Report

Usage in nterm IPython:
    %load sample_scripts/version_audit.py
    # Execute cell (Shift+Enter), then:
    version_audit(api)
    version_audit(api, folder="Production")
"""

import csv
from datetime import datetime
from pathlib import Path


def extract_version_info(result):
    """Extract version information from parsed show version output."""
    info = {
        'version': 'unknown',
        'hardware': 'unknown',
        'serial': 'unknown',
        'uptime': 'unknown',
    }
    
    if not result.parsed_data:
        return info
    
    data = result.parsed_data[0] if result.parsed_data else {}
    
    # Extract version
    for field in ['VERSION', 'version', 'SOFTWARE', 'software']:
        if field in data and data[field]:
            info['version'] = data[field]
            break
    
    # Extract hardware
    for field in ['HARDWARE', 'hardware', 'MODEL', 'model', 'PLATFORM', 'platform']:
        if field in data and data[field]:
            info['hardware'] = data[field]
            break
    
    # Extract serial
    for field in ['SERIAL', 'serial', 'SERIAL_NUMBER', 'serial_number']:
        if field in data:
            serial = data[field]
            if isinstance(serial, list) and serial:
                info['serial'] = serial[0]
            elif serial:
                info['serial'] = str(serial)
            if info['serial'] != 'unknown':
                break
    
    # Extract uptime
    for field in ['UPTIME', 'uptime']:
        if field in data and data[field]:
            info['uptime'] = data[field]
            break
    
    return info


def audit_device(api, device):
    """Audit a single device."""
    session = None
    try:
        session = api.connect(device.name)
        
        if not session.is_connected():
            return {
                'device_name': device.name,
                'hostname': device.hostname,
                'platform': 'unknown',
                'version': 'CONNECTION FAILED',
                'hardware': '',
                'serial': '',
                'uptime': '',
                'status': 'failed',
            }
        
        platform = session.platform or 'unknown'
        result = api.send(session, "show version", timeout=60)
        info = extract_version_info(result)
        
        return {
            'device_name': device.name,
            'hostname': device.hostname,
            'platform': platform,
            'version': info['version'],
            'hardware': info['hardware'],
            'serial': info['serial'],
            'uptime': info['uptime'],
            'status': 'success',
        }
        
    except Exception as e:
        return {
            'device_name': device.name,
            'hostname': device.hostname,
            'platform': 'unknown',
            'version': f'ERROR: {str(e)}',
            'hardware': '',
            'serial': '',
            'uptime': '',
            'status': 'error',
        }
        
    finally:
        if session and session.is_connected():
            try:
                api.disconnect(session)
            except:
                pass


def version_audit(api, folder=None, output_base="version_audit", vault_password=None):
    """
    Audit software versions across network devices.
    
    Args:
        api: NTermAPI instance
        folder: Target folder name (None = all devices)
        output_base: Base name for output CSV file
        vault_password: Vault password (None = must be unlocked already)
    
    Returns:
        list: Audit results for all devices
    """
    print("\n" + "="*70)
    print("Network Device Version Audit")
    print("="*70 + "\n")
    
    # Unlock vault if needed
    if not api.vault_unlocked:
        if vault_password:
            print("Unlocking vault...")
            api.unlock(vault_password)
        else:
            print("ERROR: Vault is locked. Pass vault_password or unlock manually.")
            return []
    
    # Get devices
    if folder:
        print(f"Target folder: {folder}")
        devices = api.devices(folder=folder)
    else:
        print("Target: All devices")
        devices = api.devices()
    
    if not devices:
        print("No devices found.")
        return []
    
    print(f"Found {len(devices)} device(s)\n")
    print("Collecting version information...\n")
    
    # Audit each device
    results = []
    
    for i, device in enumerate(devices, 1):
        print(f"[{i}/{len(devices)}] {device.name} ({device.hostname})... ", end='', flush=True)
        
        result = audit_device(api, device)
        results.append(result)
        
        if result['status'] == 'success':
            print(f"✓ {result['platform']}")
        else:
            print("❌")
    
    # Generate CSV
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"{output_base}_{timestamp}.csv"
    
    print(f"\nWriting report to: {output_file}")
    
    fieldnames = ['device_name', 'hostname', 'platform', 'version', 'hardware', 'serial', 'uptime']
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            row = {k: result[k] for k in fieldnames}
            writer.writerow(row)
    
    # Summary
    success_count = sum(1 for r in results if r['status'] == 'success')
    failed_count = len(results) - success_count
    
    print("\n" + "="*70)
    print("Audit Summary")
    print("="*70)
    print(f"\nTotal devices:  {len(results)}")
    print(f"Successful:     {success_count}")
    print(f"Failed:         {failed_count}")
    
    if failed_count > 0:
        print("\nFailed devices:")
        for result in results:
            if result['status'] != 'success':
                print(f"  ❌ {result['device_name']}: {result['version']}")
    
    print(f"\nReport saved to: {output_file}")
    print("\n" + "="*70 + "\n")
    
    # Display sample
    print("Sample results:")
    print("-" * 70)
    for result in results[:5]:
        if result['status'] == 'success':
            print(f"{result['device_name']:20} {result['platform']:15} {result['version'][:30]}")
    if len(results) > 5:
        print(f"... and {len(results) - 5} more devices")
    print()
    
    return results
