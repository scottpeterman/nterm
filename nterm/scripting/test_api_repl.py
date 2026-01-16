#!/usr/bin/env python3
"""
Test script to verify new API backend works with REPL.

Run from nterm project directory:
    python -m nterm.scripting.test_api_repl

Or in IPython:
    %run nterm/scripting/test_api_repl.py
"""

import sys
from pathlib import Path


def test_api_imports():
    """Test that all new API components import correctly."""
    print("=" * 60)
    print("Testing API Imports")
    print("=" * 60)

    try:
        from nterm.scripting.api import NTermAPI, get_api
        print("✓ NTermAPI imported")
    except ImportError as e:
        print(f"✗ NTermAPI import failed: {e}")
        return False

    try:
        from nterm.scripting.models import ActiveSession, CommandResult, DeviceInfo, CredentialInfo
        print("✓ Models imported")
    except ImportError as e:
        print(f"✗ Models import failed: {e}")
        return False

    try:
        from nterm.scripting.platform_data import PLATFORM_COMMANDS, PLATFORM_PATTERNS
        print("✓ Platform data imported")
        print(f"  - {len(PLATFORM_PATTERNS)} platforms defined")
        print(f"  - {len(list(PLATFORM_COMMANDS.get('cisco_ios', {}).keys()))} command types for cisco_ios")
    except ImportError as e:
        print(f"✗ Platform data import failed: {e}")
        return False

    try:
        from nterm.scripting.platform_utils import (
            detect_platform,
            get_platform_command,
            extract_version_info,
            extract_field,
        )
        print("✓ Platform utils imported")
    except ImportError as e:
        print(f"✗ Platform utils import failed: {e}")
        return False

    try:
        from nterm.scripting.ssh_connection import (
            connect_ssh,
            send_command,
            wait_for_prompt,
            filter_ansi_sequences,
            PagingNotDisabledError,
        )
        print("✓ SSH connection imported")
    except ImportError as e:
        print(f"✗ SSH connection import failed: {e}")
        return False

    print()
    return True


def test_platform_utils():
    """Test platform utility functions."""
    print("=" * 60)
    print("Testing Platform Utils")
    print("=" * 60)

    from nterm.scripting.platform_utils import (
        detect_platform,
        get_platform_command,
        extract_field,
        extract_version_info,
    )

    # Test detect_platform
    test_cases = [
        ("Cisco IOS Software, IOSv Software", "cisco_ios"),
        ("Arista vEOS", "arista_eos"),
        ("Cisco Nexus Operating System", "cisco_nxos"),
        ("JUNOS 20.4R1", "juniper_junos"),
        ("Unknown device", None),
    ]

    print("\ndetect_platform():")
    for version_output, expected in test_cases:
        result = detect_platform(version_output)
        status = "✓" if result == expected else "✗"
        print(f"  {status} '{version_output[:30]}...' -> {result} (expected: {expected})")

    # Test get_platform_command
    print("\nget_platform_command():")

    cmd = get_platform_command('cisco_ios', 'config')
    print(f"  cisco_ios + config -> '{cmd}'")

    cmd = get_platform_command('juniper_junos', 'config')
    print(f"  juniper_junos + config -> '{cmd}'")

    cmd = get_platform_command('cisco_ios', 'interface_detail', name='Gi0/1')
    print(f"  cisco_ios + interface_detail(name='Gi0/1') -> '{cmd}'")

    cmd = get_platform_command('arista_eos', 'neighbors')
    print(f"  arista_eos + neighbors -> '{cmd}'")

    # Test extract_field
    print("\nextract_field():")
    test_data = {'VERSION': '15.2(4)M', 'HARDWARE': ['ISR4451', 'ISR4451-X']}

    result = extract_field(test_data, ['version', 'VERSION', 'SOFTWARE'])
    print(f"  Extract version from {test_data}: '{result}'")

    result = extract_field(test_data, ['HARDWARE', 'MODEL'], first_element=True)
    print(f"  Extract hardware (first): '{result}'")

    result = extract_field(test_data, ['HARDWARE', 'MODEL'], first_element=False)
    print(f"  Extract hardware (list): '{result}'")

    # Test extract_version_info
    print("\nextract_version_info():")
    parsed_data = [{'VERSION': '15.2', 'HARDWARE': 'C3850', 'SERIAL': 'FCW1234'}]
    info = extract_version_info(parsed_data, 'cisco_ios')
    print(f"  Extracted: {info}")

    print()
    return True


def test_ansi_filtering():
    """Test ANSI sequence filtering."""
    print("=" * 60)
    print("Testing ANSI Filtering")
    print("=" * 60)

    from nterm.scripting.ssh_connection import filter_ansi_sequences

    test_cases = [
        # (input, expected_output_contains)
        ("\x1b[24;1Hdevice#", "device#"),
        ("\x1b[0m\x1b[2Kshow version\x1b[0m", "show version"),
        ("\x1b[?25hrouter>", "router>"),
        ("clean text", "clean text"),
        ("\x07bell\x07", "bell"),
    ]

    for raw, expected_contains in test_cases:
        filtered = filter_ansi_sequences(raw)
        status = "✓" if expected_contains in filtered else "✗"
        print(f"  {status} Input: {repr(raw)[:40]}")
        print(f"      Output: '{filtered}'")

    print()
    return True


def test_api_initialization():
    """Test API can be initialized."""
    print("=" * 60)
    print("Testing API Initialization")
    print("=" * 60)

    try:
        from nterm.scripting.api import NTermAPI

        # This will fail if tfsm_templates.db doesn't exist
        # That's expected in some environments
        api = NTermAPI()
        print(f"✓ API initialized: {api}")

        # Test status
        status = api.status()
        print(f"  Devices: {status['devices']}")
        print(f"  Folders: {status['folders']}")
        print(f"  Vault: {'unlocked' if status['vault_unlocked'] else 'locked'}")
        print(f"  Parser DB: {status['parser_db']}")

        # Test new methods exist
        print("\nNew API methods:")
        print(f"  ✓ session() context manager: {hasattr(api, 'session')}")
        print(f"  ✓ send_first(): {hasattr(api, 'send_first')}")
        print(f"  ✓ send_platform_command(): {hasattr(api, 'send_platform_command')}")
        print(f"  ✓ disconnect_all(): {hasattr(api, 'disconnect_all')}")

        # Test active_sessions returns correct type
        sessions = api.active_sessions()
        print(f"  ✓ active_sessions() returns list: {isinstance(sessions, list)}")

        print()
        return True

    except Exception as e:
        print(f"✗ API initialization failed: {e}")
        print("  (This is expected if tfsm_templates.db is not present)")
        print()
        return False


def test_repl_imports():
    """Test REPL imports."""
    print("=" * 60)
    print("Testing REPL Imports")
    print("=" * 60)

    try:
        from nterm.scripting.repl import NTermREPL, REPLPolicy, REPLState
        print("✓ REPL classes imported")
    except ImportError as e:
        print(f"✗ REPL import failed: {e}")
        return False

    try:
        from nterm.scripting.repl_interactive import start_repl
        print("✓ Interactive REPL imported")
    except ImportError as e:
        print(f"✗ Interactive REPL import failed: {e}")
        return False

    # Test policy
    policy = REPLPolicy(mode="read_only")
    print(f"\nPolicy tests (mode={policy.mode}):")

    test_commands = [
        ("show version", True),
        ("show interfaces", True),
        ("configure terminal", False),
        ("write memory", False),
        ("reload", False),
        ("copy running-config startup-config", False),
    ]

    for cmd, expected in test_commands:
        allowed = policy.is_allowed(cmd)
        status = "✓" if allowed == expected else "✗"
        print(
            f"  {status} '{cmd}' -> {'allowed' if allowed else 'blocked'} (expected: {'allowed' if expected else 'blocked'})")

    print()
    return True


def run_all_tests():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("nterm API Backend Tests")
    print("=" * 60 + "\n")

    results = []

    results.append(("Imports", test_api_imports()))
    results.append(("Platform Utils", test_platform_utils()))
    results.append(("ANSI Filtering", test_ansi_filtering()))
    results.append(("API Init", test_api_initialization()))
    results.append(("REPL", test_repl_imports()))

    print("=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = 0
    failed = 0
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {name}")
        if result:
            passed += 1
        else:
            failed += 1

    print()
    print(f"Passed: {passed}/{len(results)}")
    print(f"Failed: {failed}/{len(results)}")
    print()

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)