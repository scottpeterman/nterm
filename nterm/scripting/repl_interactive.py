"""
nterm Interactive REPL

Launch with: api.repl()

Provides a safe, policy-controlled interface to network devices.
Same interface used by both humans (IPython) and MCP tools.
"""

from nterm.scripting.repl import NTermREPL, REPLPolicy
from .api import NTermAPI
from typing import Optional
import sys
import getpass


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
        from nterm.scripting import api as default_api
        api = default_api

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
        # Don't crash startup if db_info fails
        pass

    print()
    print("Type :help for commands, :exit to quit")
    print()

    # Interactive loop
    try:
        while True:
            # Show prompt with mode indicator
            if repl.state.connected_device:
                mode_indicator = "📊" if repl.state.output_mode == "parsed" else "📄"
                hint = f"[{repl.state.platform_hint}]" if repl.state.platform_hint else ""
                prompt = f"{mode_indicator} {repl.state.connected_device}{hint}> "
            else:
                prompt = "nterm> "

            try:
                line = input(prompt)
            except EOFError:
                # Ctrl+D
                break
            except KeyboardInterrupt:
                # Ctrl+C
                print()
                continue

            # Handle command
            result = repl.handle_line(line)

            # Display result
            if not result.get("ok"):
                print(f"Error: {result.get('error')}")
                continue

            data = result.get("data", {})
            cmd_type = data.get("type")

            if cmd_type == "exit":
                break
            elif cmd_type == "unlock_prompt":
                # Securely prompt for password
                try:
                    password = getpass.getpass("Enter vault password: ")
                    unlock_result = repl.do_unlock(password)
                    if unlock_result.get("ok"):
                        unlock_data = unlock_result.get("data", {})
                        if unlock_data.get("vault_unlocked"):
                            print("Vault unlocked")
                        else:
                            print("Unlock failed - incorrect password")
                    else:
                        print(f"Error: {unlock_result.get('error')}")
                except KeyboardInterrupt:
                    print("\nUnlock cancelled")
                    continue
            elif cmd_type == "help":
                print(data.get("text", ""))
            elif cmd_type == "unlock":
                status = "unlocked" if data.get("vault_unlocked") else "failed"
                print(f"Vault: {status}")
            elif cmd_type == "lock":
                print("Vault locked")
            elif cmd_type == "credentials":
                creds = data.get("credentials", [])
                if not creds:
                    print("No credentials found")
                else:
                    print(f"\n{'Name':<20} {'Username':<20} {'Type':<15}")
                    print("-" * 55)
                    for cred in creds:
                        print(f"{cred['name']:<20} {cred.get('username', ''):<20} {cred.get('cred_type', 'ssh'):<15}")
                    print()
            elif cmd_type == "devices":
                devices = data.get("devices", [])
                if not devices:
                    print("No devices found")
                else:
                    print(f"\n{'Name':<20} {'Hostname':<20} {'Folder':<15}")
                    print("-" * 55)
                    for dev in devices:
                        print(f"{dev['name']:<20} {dev['hostname']:<20} {dev.get('folder', ''):<15}")
                    print()
            elif cmd_type == "connect":
                print(f"Connected to {data['device']} ({data['hostname']}:{data['port']})")
                print(f"Platform: {data.get('platform', 'unknown')}")
                print(f"Prompt: {data.get('prompt', '')}")
            elif cmd_type == "disconnect":
                print("Disconnected")
            elif cmd_type == "policy":
                print(f"Policy mode: {data.get('mode')}")
            elif cmd_type == "mode":
                mode = data.get('mode')
                hint = data.get('platform_hint')
                if mode:
                    print(f"Output mode: {mode}")
                else:
                    print(f"Current mode: {mode}")
                    if hint:
                        print(f"Platform hint: {hint}")
            elif cmd_type == "format":
                fmt = data.get('format')
                print(f"Output format: {fmt}")
            elif cmd_type == "set_hint":
                print(f"Platform hint set to: {data.get('platform_hint')}")
            elif cmd_type == "clear_hint":
                print("Platform hint cleared (using auto-detection)")
            elif cmd_type == "debug":
                status = "ON" if data.get("debug_mode") else "OFF"
                print(f"Debug mode: {status}")
            elif cmd_type == "dbinfo":
                db_info = data.get("db_info", {})
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

                    # Health checks
                    if db_size == 0:
                        print("\n⚠️  WARNING: Database file is empty (0 bytes)!")
                        print("   Parsing will fail until you download templates.")
                        print("   Run: api.download_templates() or use the templates installer.")
                    elif db_size < 100000:  # Less than 100KB
                        print(f"\n⚠️  WARNING: Database seems too small ({db_size_mb:.1f} MB)")
                        print("   Expected size is ~0.3 MB. May be corrupted or incomplete.")
                    else:
                        print("\n✓ Database appears healthy")
                else:
                    print("\n❌ ERROR: Database file not found!")
                    print("   Run: api.download_templates() to create it.")

                print()
            elif cmd_type == "result":
                result_data = data.get("result", {})

                # Debug mode: show full result dict
                if repl.state.debug_mode:
                    print("\n[DEBUG - Full Result Dict]")
                    print("-" * 60)
                    import json
                    # Don't print raw_output in debug to avoid clutter
                    debug_data = {k: v for k, v in result_data.items() if k != "raw_output"}
                    print(json.dumps(debug_data, indent=2))
                    print("-" * 60)

                # Show parsed data if available
                parsed = result_data.get("parsed_data")
                parse_success = result_data.get("parse_success", False)
                platform = result_data.get("platform", "")

                # Display based on mode and format
                if repl.state.output_mode == "parsed":
                    if parsed and parse_success:
                        print(f"\n[Parsed with {platform} - format: {repl.state.output_format}]")
                        print("-" * 60)
                        _display_parsed_result(parsed, repl.state.output_format)
                        print()
                    elif parse_success and not parsed:
                        # Parsing succeeded but returned empty/no data
                        print(f"\n[Parsed with {platform} - no structured data]")
                        raw = result_data.get("raw_output", "")
                        print(raw)
                    elif parsed is None and not parse_success:
                        # Parsing failed or wasn't attempted
                        print(f"\n[Parse failed - showing raw output]")
                        raw = result_data.get("raw_output", "")
                        print(raw)
                    else:
                        # Fallback
                        raw = result_data.get("raw_output", "")
                        print(raw)
                else:
                    # Raw mode - just show output
                    raw = result_data.get("raw_output", "")
                    print(raw)

                # Show timing
                elapsed = result_data.get("elapsed_seconds", 0)
                print(f"\n[{elapsed}s]")
            elif cmd_type == "noop":
                pass
            else:
                # Unknown type, show raw data
                import json
                print(json.dumps(data, indent=2))

    finally:
        # Clean up
        if repl.state.session:
            print("\nDisconnecting...")
            repl._safe_disconnect()
        print("\nREPL closed")


def _print_parsed_data(data, max_rows=20):
    """Pretty print parsed data (list of dicts) in text format."""
    if not data:
        print("(empty)")
        return

    if not isinstance(data, list):
        import json
        print(json.dumps(data, indent=2))
        return

    # Get all unique keys
    all_keys = set()
    for row in data:
        if isinstance(row, dict):
            all_keys.update(row.keys())

    keys = sorted(all_keys)

    if not keys:
        import json
        print(json.dumps(data, indent=2))
        return

    # Calculate column widths
    col_widths = {}
    for key in keys:
        col_widths[key] = len(key)

    for row in data[:max_rows]:
        if isinstance(row, dict):
            for key in keys:
                val = str(row.get(key, ""))
                col_widths[key] = max(col_widths[key], len(val))

    # Cap widths
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


def _print_parsed_data_rich(data, max_rows=20):
    """Pretty print parsed data using Rich library."""
    try:
        from rich.console import Console
        from rich.table import Table
    except ImportError:
        print("⚠️  Rich library not available, falling back to text format")
        _print_parsed_data(data, max_rows)
        return

    if not data:
        print("(empty)")
        return

    if not isinstance(data, list):
        import json
        print(json.dumps(data, indent=2))
        return

    # Get all unique keys
    all_keys = set()
    for row in data:
        if isinstance(row, dict):
            all_keys.update(row.keys())

    keys = sorted(all_keys)

    if not keys:
        import json
        print(json.dumps(data, indent=2))
        return

    # Create rich table
    console = Console()
    table = Table(show_header=True, header_style="bold cyan")

    # Add columns
    for key in keys:
        table.add_column(key, style="white", no_wrap=False, max_width=30)

    # Add rows
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


def _print_parsed_data_json(data):
    """Print parsed data as JSON."""
    import json
    print(json.dumps(data, indent=2))


def _display_parsed_result(data, output_format, max_rows=20):
    """Display parsed data in the specified format."""
    if output_format == "json":
        _print_parsed_data_json(data)
    elif output_format == "rich":
        _print_parsed_data_rich(data, max_rows)
    else:  # text or fallback
        _print_parsed_data(data, max_rows)


# Convenience function to add to API
def add_repl_to_api(api_instance):
    """Add repl() method to API instance."""

    def repl(policy: Optional[REPLPolicy] = None):
        """Start interactive REPL."""
        start_repl(api=api_instance, policy=policy)

    api_instance.repl = repl