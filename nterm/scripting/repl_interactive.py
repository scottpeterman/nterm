"""
nterm Interactive REPL

Launch with: api.repl()

Provides a safe, policy-controlled interface to network devices.
Same interface used by both humans (IPython) and MCP tools.
"""

import sys
import getpass
import json
from typing import Optional, Dict

from .repl import NTermREPL, REPLPolicy
from .api import NTermAPI


def start_repl(api: Optional[NTermAPI] = None, policy: Optional[REPLPolicy] = None):
    """
    Start interactive REPL in IPython or terminal.

    Args:
        api: NTermAPI instance (creates default if None)
        policy: REPLPolicy (uses read_only default if None)

    Examples:
        # Default read-only mode
        api.repl()

        # Operations mode (allows config changes)
        policy = REPLPolicy(mode="ops")
        api.repl(policy=policy)

        # Custom policy
        policy = REPLPolicy(
            mode="read_only",
            deny_substrings=["reload", "wr"],
            allow_prefixes=["show", "display"],
        )
        api.repl(policy=policy)
    """
    if api is None:
        from .api import NTermAPI
        api = NTermAPI()

    repl = NTermREPL(api=api, policy=policy)

    print()
    print("=" * 60)
    print("nterm REPL - Safe Network Automation Interface")
    print("=" * 60)
    print()
    print(f"Policy: {repl.state.policy.mode}")
    print(f"Output: {repl.state.output_mode} ({repl.state.output_format})")
    print(f"Vault: {'unlocked' if api.vault_unlocked else 'locked'}")

    # Check TextFSM database health
    try:
        db_info = api.db_info()
        db_size = db_info.get('db_size', 0)
        if not db_info.get('db_exists'):
            print(f"\n⚠️  TextFSM database not found!")
            print(f"   Parsing will be unavailable. Use :dbinfo for details.")
        elif db_size == 0:
            print(f"\n⚠️  TextFSM database is empty (0 bytes)!")
            print(f"   Parsing will fail. Use :dbinfo for details.")
        elif db_size < 100000:
            print(f"\n⚠️  TextFSM database seems small ({db_info.get('db_size_mb', 0):.1f} MB)")
            print(f"   Expected ~0.3 MB. Use :dbinfo to check.")
    except Exception:
        pass

    print()
    print("Type :help for commands, :exit to quit")
    print()

    # Interactive loop
    try:
        while True:
            prompt = _build_prompt(repl)

            try:
                line = input(prompt)
            except EOFError:
                break
            except KeyboardInterrupt:
                print()
                continue

            # Handle command
            result = repl.handle_line(line)

            # Display result
            _display_result(repl, result)

            # Check for exit
            if result.get("ok") and result.get("data", {}).get("type") == "exit":
                break

    finally:
        # Clean up
        count = repl.state.api.disconnect_all()
        if count > 0:
            print(f"\nDisconnected {count} session(s)")
        print("REPL closed")


def _build_prompt(repl: NTermREPL) -> str:
    """Build the prompt string based on current state."""
    if repl.state.connected_device:
        mode_indicator = "📊" if repl.state.output_mode == "parsed" else "📄"
        hint = f"[{repl.state.platform_hint}]" if repl.state.platform_hint else ""
        return f"{mode_indicator} {repl.state.connected_device}{hint}> "
    else:
        return "nterm> "


def _display_result(repl: NTermREPL, result: Dict) -> None:
    """Display REPL result based on type."""
    if not result.get("ok"):
        print(f"Error: {result.get('error')}")
        return

    data = result.get("data", {})
    cmd_type = data.get("type")

    # ===== Vault Commands =====
    if cmd_type == "unlock_prompt":
        try:
            password = getpass.getpass("Enter vault password: ")
            unlock_result = repl.do_unlock(password)
            if unlock_result.get("ok"):
                if unlock_result.get("data", {}).get("vault_unlocked"):
                    print("✓ Vault unlocked")
                else:
                    print("✗ Unlock failed - incorrect password")
            else:
                print(f"Error: {unlock_result.get('error')}")
        except KeyboardInterrupt:
            print("\nUnlock cancelled")
        return

    if cmd_type == "unlock":
        status = "unlocked" if data.get("vault_unlocked") else "failed"
        print(f"Vault: {status}")
        return

    if cmd_type == "lock":
        print("✓ Vault locked")
        return

    # ===== Inventory Commands =====
    if cmd_type == "credentials":
        creds = data.get("credentials", [])
        if not creds:
            print("No credentials found")
        else:
            print(f"\n{'Name':<20} {'Username':<20} {'Auth':<15} {'Default':<8}")
            print("-" * 63)
            for cred in creds:
                auth_types = []
                if cred.get('has_password'):
                    auth_types.append('pass')
                if cred.get('has_key'):
                    auth_types.append('key')
                auth = '+'.join(auth_types) if auth_types else 'none'
                default = '★' if cred.get('is_default') else ''
                print(f"{cred['name']:<20} {cred.get('username', ''):<20} {auth:<15} {default:<8}")
            print()
        return

    if cmd_type == "devices":
        devices = data.get("devices", [])
        if not devices:
            print("No devices found")
        else:
            print(f"\n{'Name':<25} {'Hostname':<20} {'Port':<6} {'Folder':<15}")
            print("-" * 66)
            for dev in devices:
                print(f"{dev['name']:<25} {dev['hostname']:<20} {dev.get('port', 22):<6} {dev.get('folder', ''):<15}")
            print(f"\n{len(devices)} device(s)")
        return

    if cmd_type == "folders":
        folders = data.get("folders", [])
        if not folders:
            print("No folders found")
        else:
            print("\nFolders:")
            for f in sorted(folders):
                print(f"  📁 {f}")
            print()
        return

    # ===== Session Commands =====
    if cmd_type == "connect":
        print(f"✓ Connected to {data['device']} ({data['hostname']}:{data['port']})")
        print(f"  Platform: {data.get('platform', 'unknown')}")
        print(f"  Prompt: {data.get('prompt', '')}")
        return

    if cmd_type == "disconnect":
        msg = data.get("message", "Disconnected")
        print(f"✓ {msg}")
        return

    if cmd_type == "sessions":
        sessions = data.get("sessions", [])
        current = data.get("current")
        if not sessions:
            print("No active sessions")
        else:
            print(f"\n{'Device':<20} {'Hostname':<20} {'Platform':<15} {'Status':<10}")
            print("-" * 65)
            for s in sessions:
                marker = "→ " if s['device'] == current else "  "
                status = "connected" if s.get('connected') else "stale"
                print(f"{marker}{s['device']:<18} {s['hostname']:<20} {s.get('platform', 'unknown'):<15} {status:<10}")
            print()
        return

    # ===== Settings Commands =====
    if cmd_type == "policy":
        mode = data.get('mode')
        emoji = "🔒" if mode == "read_only" else "⚡"
        print(f"Policy mode: {emoji} {mode}")
        return

    if cmd_type == "mode":
        mode = data.get('mode')
        hint = data.get('platform_hint')
        print(f"Output mode: {mode}")
        if hint:
            print(f"Platform hint: {hint}")
        return

    if cmd_type == "format":
        print(f"Output format: {data.get('format')}")
        return

    if cmd_type == "set_hint":
        print(f"✓ Platform hint set to: {data.get('platform_hint')}")
        return

    if cmd_type == "clear_hint":
        print("✓ Platform hint cleared (using auto-detection)")
        return

    if cmd_type == "debug":
        status = "ON" if data.get("debug_mode") else "OFF"
        print(f"Debug mode: {status}")
        return

    # ===== Info Commands =====
    if cmd_type == "dbinfo":
        _display_dbinfo(data.get("db_info", {}))
        return

    if cmd_type == "help":
        print(data.get("text", ""))
        return

    if cmd_type == "exit":
        count = data.get("disconnected", 0)
        if count > 0:
            print(f"Disconnected {count} session(s)")
        return

    if cmd_type == "noop":
        return

    # ===== Quick Commands =====
    if cmd_type == "version":
        result_data = data.get("result", {})
        version_info = result_data.get("version_info", {})

        print(f"\n{'─' * 50}")
        print(f"  Version:  {version_info.get('version', 'unknown')}")
        print(f"  Hardware: {version_info.get('hardware', 'unknown')}")
        print(f"  Serial:   {version_info.get('serial', 'unknown')}")
        print(f"  Uptime:   {version_info.get('uptime', 'unknown')}")
        print(f"{'─' * 50}")

        elapsed = result_data.get("elapsed_seconds", 0)
        print(f"[{elapsed}s]")
        return

    if cmd_type == "neighbors":
        result_data = data.get("result", {})
        neighbor_info = result_data.get("neighbor_info", [])

        if not neighbor_info:
            parsed = result_data.get("parsed_data", [])
            if parsed:
                # Fall back to raw parsed data
                _display_parsed_result(parsed, repl.state.output_format)
            else:
                print("No neighbors found")
        else:
            print(f"\n{'Local Interface':<20} {'Neighbor':<30} {'Remote Port':<20} {'Platform':<20}")
            print("-" * 90)
            for n in neighbor_info:
                print(f"{n.get('local_interface', 'unknown'):<20} "
                      f"{n.get('neighbor_device', 'unknown'):<30} "
                      f"{n.get('neighbor_interface', 'unknown'):<20} "
                      f"{n.get('platform', '')[:20]:<20}")
            print(f"\n{len(neighbor_info)} neighbor(s)")

        elapsed = result_data.get("elapsed_seconds", 0)
        print(f"[{elapsed}s]")
        return

    # ===== Generic Result =====
    if cmd_type == "result":
        result_data = data.get("result", {})
        _display_command_result(repl, result_data)
        return

    # Unknown type - dump as JSON
    print(json.dumps(data, indent=2))


def _display_command_result(repl: NTermREPL, result_data: Dict) -> None:
    """Display a generic command result."""
    # Debug mode: show full result dict
    if repl.state.debug_mode:
        print("\n[DEBUG - Full Result Dict]")
        print("-" * 60)
        debug_data = {k: v for k, v in result_data.items() if k != "raw_output"}
        print(json.dumps(debug_data, indent=2, default=str))
        print("-" * 60)

    parsed = result_data.get("parsed_data")
    parse_success = result_data.get("parse_success", False)
    platform = result_data.get("platform", "")
    command_type = result_data.get("command_type", "")

    # Display based on mode
    if repl.state.output_mode == "parsed":
        if parsed and parse_success:
            header = f"[Parsed: {platform}"
            if command_type:
                header += f" | {command_type}"
            header += f" | format: {repl.state.output_format}]"
            print(f"\n{header}")
            print("-" * 60)
            _display_parsed_result(parsed, repl.state.output_format)
            print()
        elif parse_success and not parsed:
            print(f"\n[Parsed: {platform} - no structured data]")
            raw = result_data.get("raw_output", "")
            print(raw)
        elif not parse_success:
            print(f"\n[Parse failed - showing raw output]")
            raw = result_data.get("raw_output", "")
            print(raw)
        else:
            raw = result_data.get("raw_output", "")
            print(raw)
    else:
        # Raw mode
        raw = result_data.get("raw_output", "")
        print(raw)

    # Show timing
    elapsed = result_data.get("elapsed_seconds", 0)
    print(f"\n[{elapsed}s]")


def _display_dbinfo(db_info: Dict) -> None:
    """Display TextFSM database info."""
    print("\nTextFSM Database Info:")
    print("=" * 60)
    print(f"Engine Available:  {db_info.get('engine_available', False)}")
    print(f"Database Path:     {db_info.get('db_path', 'unknown')}")
    print(f"Database Exists:   {db_info.get('db_exists', False)}")

    if db_info.get('db_exists'):
        db_size = db_info.get('db_size', 0)
        db_size_mb = db_info.get('db_size_mb', 0.0)
        print(f"Database Size:     {db_size:,} bytes ({db_size_mb:.1f} MB)")
        print(f"Absolute Path:     {db_info.get('db_absolute_path', 'unknown')}")

        if db_size == 0:
            print("\n⚠️  WARNING: Database file is empty (0 bytes)!")
            print("   Parsing will fail until you download templates.")
        elif db_size < 100000:
            print(f"\n⚠️  WARNING: Database seems too small ({db_size_mb:.1f} MB)")
            print("   Expected size is ~0.3 MB. May be corrupted or incomplete.")
        else:
            print("\n✓ Database appears healthy")
    else:
        print("\n✗ ERROR: Database file not found!")
        print("   Run: api.download_templates() to create it.")

    print()


def _display_parsed_result(data, output_format: str, max_rows: int = 20) -> None:
    """Display parsed data in the specified format."""
    if output_format == "json":
        print(json.dumps(data, indent=2, default=str))
    elif output_format == "rich":
        _print_parsed_data_rich(data, max_rows)
    else:
        _print_parsed_data_text(data, max_rows)


def _print_parsed_data_text(data, max_rows: int = 20) -> None:
    """Pretty print parsed data as text table."""
    if not data:
        print("(empty)")
        return

    if not isinstance(data, list):
        print(json.dumps(data, indent=2, default=str))
        return

    # Get all unique keys
    all_keys = set()
    for row in data:
        if isinstance(row, dict):
            all_keys.update(row.keys())

    keys = sorted(all_keys)

    if not keys:
        print(json.dumps(data, indent=2, default=str))
        return

    # Calculate column widths
    col_widths = {key: len(key) for key in keys}

    for row in data[:max_rows]:
        if isinstance(row, dict):
            for key in keys:
                val = str(row.get(key, ""))
                col_widths[key] = max(col_widths[key], len(val))

    # Cap widths at 30
    for key in keys:
        col_widths[key] = min(col_widths[key], 30)

    # Print header
    header = " | ".join(key[:col_widths[key]].ljust(col_widths[key]) for key in keys)
    print(header)
    print("-" * len(header))

    # Print rows
    shown = 0
    for row in data:
        if not isinstance(row, dict):
            continue
        if shown >= max_rows:
            remaining = len(data) - shown
            print(f"... ({remaining} more rows)")
            break

        values = []
        for key in keys:
            val = str(row.get(key, ""))
            if len(val) > col_widths[key]:
                val = val[:col_widths[key] - 3] + "..."
            values.append(val.ljust(col_widths[key]))

        print(" | ".join(values))
        shown += 1


def _print_parsed_data_rich(data, max_rows: int = 20) -> None:
    """Pretty print parsed data using Rich library."""
    try:
        from rich.console import Console
        from rich.table import Table
    except ImportError:
        print("⚠️  Rich library not available, falling back to text format")
        _print_parsed_data_text(data, max_rows)
        return

    if not data:
        print("(empty)")
        return

    if not isinstance(data, list):
        print(json.dumps(data, indent=2, default=str))
        return

    # Get all unique keys
    all_keys = set()
    for row in data:
        if isinstance(row, dict):
            all_keys.update(row.keys())

    keys = sorted(all_keys)

    if not keys:
        print(json.dumps(data, indent=2, default=str))
        return

    # Create rich table
    console = Console()
    table = Table(show_header=True, header_style="bold cyan")

    for key in keys:
        table.add_column(key, style="white", no_wrap=False, max_width=30)

    shown = 0
    for row in data:
        if not isinstance(row, dict):
            continue
        if shown >= max_rows:
            remaining = len(data) - shown
            console.print(f"[yellow]... ({remaining} more rows)[/yellow]")
            break

        values = [str(row.get(key, "")) for key in keys]
        table.add_row(*values)
        shown += 1

    console.print(table)


# Convenience function to add to API
def add_repl_to_api(api_instance: NTermAPI) -> None:
    """Add repl() method to API instance."""

    def repl(policy: Optional[REPLPolicy] = None):
        """Start interactive REPL."""
        start_repl(api=api_instance, policy=policy)

    api_instance.repl = repl


# Type hint for display function
from typing import Dict