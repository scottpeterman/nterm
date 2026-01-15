"""
interface_errors.py - Interface Error Detection

Usage in nterm IPython:
    %load sample_scripts/interface_errors.py
    # Execute cell (Shift+Enter), then:
    interface_errors(api)
    interface_errors(api, folder="Production", error_threshold=100)
"""


def check_interface_errors(api, session, device_name, error_threshold=0, check_down=True):
    """Check for interface errors on a device."""
    problems = []
    
    try:
        result = api.send(session, "show interfaces")
        
        if not result.parsed_data:
            # Try brief as fallback
            result = api.send(session, "show ip interface brief")
            if result.parsed_data:
                for intf in result.parsed_data:
                    status = intf.get('STATUS', '').lower()
                    proto = intf.get('PROTO', '').lower()
                    
                    if check_down and 'down' in status and 'down' in proto:
                        problems.append({
                            'device': device_name,
                            'interface': intf.get('interface', intf.get('INTERFACE', 'unknown')),
                            'issue': 'down/down',
                            'admin_state': status,
                            'oper_state': proto,
                            'in_errors': 0,
                            'out_errors': 0,
                            'crc_errors': 0,
                        })
            return problems
        
        # Check each interface
        for intf in result.parsed_data:
            interface_name = intf.get('INTERFACE', intf.get('interface', 'unknown'))
            
            # Get error counters
            in_errors = int(intf.get('INPUT_ERRORS', intf.get('in_errors', 0)))
            out_errors = int(intf.get('OUTPUT_ERRORS', intf.get('out_errors', 0)))
            crc_errors = int(intf.get('CRC', intf.get('crc_errors', 0)))
            
            # Get interface status
            admin_state = intf.get('LINK_STATUS', intf.get('admin_state', 'unknown')).lower()
            oper_state = intf.get('PROTOCOL_STATUS', intf.get('oper_state', 'unknown')).lower()
            
            # Check for errors
            has_errors = (in_errors > error_threshold or 
                         out_errors > error_threshold or 
                         crc_errors > error_threshold)
            
            is_down = (check_down and 'down' in admin_state and 'down' in oper_state)
            
            if has_errors or is_down:
                issue = []
                if in_errors > error_threshold:
                    issue.append(f"input_errors: {in_errors}")
                if out_errors > error_threshold:
                    issue.append(f"output_errors: {out_errors}")
                if crc_errors > error_threshold:
                    issue.append(f"crc_errors: {crc_errors}")
                if is_down:
                    issue.append("down/down")
                
                problems.append({
                    'device': device_name,
                    'interface': interface_name,
                    'issue': ', '.join(issue),
                    'admin_state': admin_state,
                    'oper_state': oper_state,
                    'in_errors': in_errors,
                    'out_errors': out_errors,
                    'crc_errors': crc_errors,
                })
        
    except Exception as e:
        print(f"      Error checking interfaces: {e}")
    
    return problems


def interface_errors(api, folder=None, error_threshold=0, check_down=True, vault_password=None):
    """
    Scan network devices for interface errors.
    
    Args:
        api: NTermAPI instance
        folder: Target folder name (None = all devices)
        error_threshold: Report errors > this value
        check_down: Report down/down interfaces
        vault_password: Vault password (None = must be unlocked already)
    
    Returns:
        list: Problematic interfaces found
    """
    print("\n" + "="*70)
    print("Interface Error Detection")
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
    
    print(f"Found {len(devices)} device(s)")
    print(f"Error threshold: >{error_threshold}")
    print(f"Check down interfaces: {check_down}\n")
    print("Scanning interfaces...\n")
    
    # Scan each device
    all_problems = []
    device_count = 0
    
    for i, device in enumerate(devices, 1):
        print(f"[{i}/{len(devices)}] {device.name} ({device.hostname})")
        
        session = None
        try:
            session = api.connect(device.name)
            
            if not session.is_connected():
                print("      ❌ Connection failed\n")
                continue
            
            device_count += 1
            
            problems = check_interface_errors(api, session, device.name, error_threshold, check_down)
            
            if problems:
                print(f"      ⚠️  Found {len(problems)} problematic interface(s)")
                all_problems.extend(problems)
            else:
                print("      ✓ All interfaces OK")
            
            print()
            
        except Exception as e:
            print(f"      ❌ Error: {e}\n")
            
        finally:
            if session and session.is_connected():
                try:
                    api.disconnect(session)
                except:
                    pass
    
    # Print results
    print("\n" + "="*70)
    print("Scan Results")
    print("="*70 + "\n")
    
    if not all_problems:
        print("✓ No interface problems detected!\n")
        return []
    
    # Group by device
    by_device = {}
    for problem in all_problems:
        device = problem['device']
        if device not in by_device:
            by_device[device] = []
        by_device[device].append(problem)
    
    print(f"Found {len(all_problems)} problematic interface(s) on {len(by_device)} device(s):\n")
    
    # Print grouped by device
    for device in sorted(by_device.keys()):
        problems = by_device[device]
        print(f"\n{device}:")
        print("-" * 70)
        
        for p in problems:
            line = f"  {p['interface']:20}"
            
            if 'down' in p['issue']:
                line += f" [{p['admin_state']}/{p['oper_state']}]"
            
            if p['in_errors'] > 0 or p['out_errors'] > 0 or p['crc_errors'] > 0:
                line += f"  IN:{p['in_errors']} OUT:{p['out_errors']} CRC:{p['crc_errors']}"
            
            print(line)
    
    # Summary
    print("\n" + "="*70)
    print("Summary")
    print("="*70)
    print(f"\nDevices scanned:        {device_count}")
    print(f"Devices with issues:    {len(by_device)}")
    print(f"Total problem intfs:    {len(all_problems)}")
    
    error_count = sum(1 for p in all_problems if 'errors' in p['issue'])
    down_count = sum(1 for p in all_problems if 'down/down' in p['issue'])
    
    if error_count > 0:
        print(f"  - With errors:        {error_count}")
    if down_count > 0:
        print(f"  - Down/down status:   {down_count}")
    
    print("\n" + "="*70 + "\n")
    
    return all_problems
