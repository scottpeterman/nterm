"""
neighbor_discovery.py - Network Topology via CDP/LLDP

Usage in nterm IPython:
    %load sample_scripts/neighbor_discovery.py
    # Execute cell (Shift+Enter), then:
    neighbor_discovery(api)
    neighbor_discovery(api, folder="Core-Switches")
"""


def get_neighbors(api, session, device_name):
    """Get CDP or LLDP neighbors from a device."""
    neighbors = []
    
    # Try CDP first
    try:
        result = api.send(session, "show cdp neighbors detail")
        
        if result.parsed_data:
            for neighbor in result.parsed_data:
                neighbors.append({
                    'source_device': device_name,
                    'local_interface': neighbor.get('LOCAL_INTERFACE', neighbor.get('local_port', 'unknown')),
                    'neighbor_device': neighbor.get('NEIGHBOR_NAME', neighbor.get('DESTINATION_HOST', 'unknown')),
                    'neighbor_interface': neighbor.get('NEIGHBOR_INTERFACE', neighbor.get('remote_port', 'unknown')),
                    'platform': neighbor.get('PLATFORM', neighbor.get('platform', 'unknown')),
                    'protocol': 'CDP',
                })
            return neighbors
    except:
        pass
    
    # Try LLDP
    try:
        result = api.send(session, "show lldp neighbors detail")
        
        if result.parsed_data:
            for neighbor in result.parsed_data:
                neighbors.append({
                    'source_device': device_name,
                    'local_interface': neighbor.get('LOCAL_INTERFACE', neighbor.get('local_port', 'unknown')),
                    'neighbor_device': neighbor.get('NEIGHBOR_NAME', neighbor.get('SYSTEM_NAME', 'unknown')),
                    'neighbor_interface': neighbor.get('NEIGHBOR_INTERFACE', neighbor.get('remote_port', 'unknown')),
                    'platform': neighbor.get('SYSTEM_DESCRIPTION', neighbor.get('platform', 'unknown')),
                    'protocol': 'LLDP',
                })
            return neighbors
    except:
        pass
    
    # Try brief commands as fallback
    try:
        result = api.send(session, "show cdp neighbors")
        if result.parsed_data:
            for neighbor in result.parsed_data:
                neighbors.append({
                    'source_device': device_name,
                    'local_interface': neighbor.get('LOCAL_INTERFACE', 'unknown'),
                    'neighbor_device': neighbor.get('NEIGHBOR', neighbor.get('NEIGHBOR_NAME', 'unknown')),
                    'neighbor_interface': neighbor.get('NEIGHBOR_INTERFACE', 'unknown'),
                    'platform': neighbor.get('PLATFORM', 'unknown'),
                    'protocol': 'CDP',
                })
            return neighbors
    except:
        pass
    
    return neighbors


def neighbor_discovery(api, folder=None, vault_password=None):
    """
    Discover network topology via CDP/LLDP neighbors.
    
    Args:
        api: NTermAPI instance
        folder: Target folder name (None = all devices)
        vault_password: Vault password (None = must be unlocked already)
    
    Returns:
        list: All neighbor relationships discovered
    """
    print("\n" + "="*70)
    print("Network Neighbor Discovery (CDP/LLDP)")
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
    print("Collecting neighbor information...\n")
    
    # Collect neighbors from all devices
    all_neighbors = []
    
    for i, device in enumerate(devices, 1):
        print(f"[{i}/{len(devices)}] {device.name}... ", end='', flush=True)
        
        session = None
        try:
            session = api.connect(device.name)
            
            if not session.is_connected():
                print("❌ connection failed")
                continue
            
            neighbors = get_neighbors(api, session, device.name)
            
            if neighbors:
                print(f"✓ found {len(neighbors)} neighbor(s)")
                all_neighbors.extend(neighbors)
            else:
                print("⚠️  no neighbors found")
            
        except Exception as e:
            print(f"❌ {e}")
            
        finally:
            if session and session.is_connected():
                try:
                    api.disconnect(session)
                except:
                    pass
    
    # Display results
    print("\n" + "="*70)
    print("Network Topology")
    print("="*70 + "\n")
    
    if not all_neighbors:
        print("No neighbor relationships discovered.\n")
        return []
    
    # Group by source device
    by_device = {}
    for neighbor in all_neighbors:
        device = neighbor['source_device']
        if device not in by_device:
            by_device[device] = []
        by_device[device].append(neighbor)
    
    # Print topology
    for device in sorted(by_device.keys()):
        neighbors = by_device[device]
        print(f"\n{device}:")
        print("-" * 70)
        
        for n in neighbors:
            # Shorten interface names
            local = n['local_interface'].replace('GigabitEthernet', 'Gi')
            local = local.replace('TenGigabitEthernet', 'Te')
            local = local.replace('Ethernet', 'Et')
            
            remote_port = n['neighbor_interface'].replace('GigabitEthernet', 'Gi')
            remote_port = remote_port.replace('TenGigabitEthernet', 'Te')
            remote_port = remote_port.replace('Ethernet', 'Et')
            
            print(f"  {local:20} -> {n['neighbor_device']:30} [{remote_port}]  ({n['protocol']})")
    
    # Summary
    print("\n" + "="*70)
    print("Summary")
    print("="*70)
    print(f"\nDevices queried:        {len(devices)}")
    print(f"Devices with neighbors: {len(by_device)}")
    print(f"Total connections:      {len(all_neighbors)}")
    
    unique_neighbors = set(n['neighbor_device'] for n in all_neighbors)
    print(f"Unique neighbors:       {len(unique_neighbors)}")
    
    cdp_count = sum(1 for n in all_neighbors if n['protocol'] == 'CDP')
    lldp_count = sum(1 for n in all_neighbors if n['protocol'] == 'LLDP')
    
    print(f"\nProtocol usage:")
    if cdp_count > 0:
        print(f"  CDP:  {cdp_count}")
    if lldp_count > 0:
        print(f"  LLDP: {lldp_count}")
    
    print("\n" + "="*70 + "\n")
    
    return all_neighbors
