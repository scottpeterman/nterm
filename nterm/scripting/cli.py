"""
nterm/scripting/cli.py

Command-line interface for nterm scripting API.

Usage:
    nterm-cli devices
    nterm-cli search leaf
    nterm-cli device eng-leaf-1
    nterm-cli credentials --unlock
    nterm-cli status
"""

import sys
import json
import getpass
from typing import Optional

import click

from .api import NTermAPI, DeviceInfo, CredentialInfo

# Shared API instance
_api: Optional[NTermAPI] = None


def get_api() -> NTermAPI:
    global _api
    if _api is None:
        _api = NTermAPI()
    return _api


def format_table(items: list, columns: list[tuple[str, str, int]]) -> str:
    """
    Format items as a simple table.

    Args:
        items: List of objects with attributes
        columns: List of (attr_name, header, width) tuples
    """
    if not items:
        return "No results."

    # Build header
    header = ""
    separator = ""
    for attr, name, width in columns:
        header += f"{name:<{width}} "
        separator += "-" * width + " "

    lines = [header.rstrip(), separator.rstrip()]

    # Build rows
    for item in items:
        row = ""
        for attr, name, width in columns:
            val = getattr(item, attr, "")
            if val is None:
                val = ""
            val_str = str(val)[:width - 1]  # Truncate if needed
            row += f"{val_str:<{width}} "
        lines.append(row.rstrip())

    return "\n".join(lines)


@click.group()
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.pass_context
def cli(ctx, output_json):
    """nterm command-line interface for device and credential management."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = output_json


@cli.command("devices")
@click.option("-p", "--pattern", default=None, help="Filter by glob pattern (e.g., 'eng-*')")
@click.option("-f", "--folder", default=None, help="Filter by folder name")
@click.pass_context
def list_devices(ctx, pattern, folder):
    """List saved devices/sessions."""
    api = get_api()
    devices = api.devices(pattern=pattern, folder=folder)

    if ctx.obj["json"]:
        click.echo(json.dumps([d.to_dict() for d in devices], indent=2))
    else:
        columns = [
            ("name", "NAME", 25),
            ("hostname", "HOSTNAME", 20),
            ("port", "PORT", 6),
            ("folder", "FOLDER", 15),
            ("credential", "CREDENTIAL", 20),
        ]
        click.echo(format_table(devices, columns))
        click.echo(f"\n{len(devices)} device(s)")


@cli.command("search")
@click.argument("query")
@click.pass_context
def search_devices(ctx, query):
    """Search devices by name, hostname, or description."""
    api = get_api()
    devices = api.search(query)

    if ctx.obj["json"]:
        click.echo(json.dumps([d.to_dict() for d in devices], indent=2))
    else:
        columns = [
            ("name", "NAME", 25),
            ("hostname", "HOSTNAME", 20),
            ("port", "PORT", 6),
            ("folder", "FOLDER", 15),
            ("credential", "CREDENTIAL", 20),
        ]
        click.echo(format_table(devices, columns))
        click.echo(f"\n{len(devices)} result(s)")


@cli.command("device")
@click.argument("name")
@click.pass_context
def get_device(ctx, name):
    """Get details for a specific device."""
    api = get_api()
    device = api.device(name)

    if not device:
        click.echo(f"Device '{name}' not found.", err=True)
        sys.exit(1)

    if ctx.obj["json"]:
        click.echo(json.dumps(device.to_dict(), indent=2))
    else:
        click.echo(f"Name:           {device.name}")
        click.echo(f"Hostname:       {device.hostname}")
        click.echo(f"Port:           {device.port}")
        click.echo(f"Folder:         {device.folder or '(root)'}")
        click.echo(f"Credential:     {device.credential or '(none)'}")
        click.echo(f"Last Connected: {device.last_connected or 'never'}")
        click.echo(f"Connect Count:  {device.connect_count}")


@cli.command("folders")
@click.pass_context
def list_folders(ctx):
    """List all folders."""
    api = get_api()
    folders = api.folders()

    if ctx.obj["json"]:
        click.echo(json.dumps(folders, indent=2))
    else:
        if folders:
            for f in folders:
                click.echo(f"  {f}")
            click.echo(f"\n{len(folders)} folder(s)")
        else:
            click.echo("No folders.")


@cli.command("credentials")
@click.option("-p", "--pattern", default=None, help="Filter by glob pattern")
@click.option("-u", "--unlock", is_flag=True, help="Prompt for vault password")
@click.option("--password", default=None, help="Vault password (use --unlock for interactive)")
@click.pass_context
def list_credentials(ctx, pattern, unlock, password):
    """List credentials (requires unlocked vault)."""
    api = get_api()

    # Handle vault unlock
    if not api.vault_initialized:
        click.echo("Vault not initialized. Run nterm to create a vault first.", err=True)
        sys.exit(1)

    if not api.vault_unlocked:
        if unlock:
            password = getpass.getpass("Vault password: ")

        if password:
            if not api.unlock(password):
                click.echo("Failed to unlock vault. Wrong password?", err=True)
                sys.exit(1)
        else:
            click.echo("Vault is locked. Use --unlock or --password to unlock.", err=True)
            sys.exit(1)

    credentials = api.credentials(pattern=pattern)

    if ctx.obj["json"]:
        click.echo(json.dumps([c.to_dict() for c in credentials], indent=2))
    else:
        columns = [
            ("name", "NAME", 20),
            ("username", "USERNAME", 15),
            ("has_password", "PASS", 5),
            ("has_key", "KEY", 5),
            ("is_default", "DEFAULT", 8),
            ("jump_host", "JUMP HOST", 20),
        ]
        click.echo(format_table(credentials, columns))
        click.echo(f"\n{len(credentials)} credential(s)")


@cli.command("credential")
@click.argument("name")
@click.option("-u", "--unlock", is_flag=True, help="Prompt for vault password")
@click.option("--password", default=None, help="Vault password")
@click.pass_context
def get_credential(ctx, name, unlock, password):
    """Get details for a specific credential."""
    api = get_api()

    # Handle vault unlock
    if not api.vault_unlocked:
        if unlock:
            password = getpass.getpass("Vault password: ")

        if password:
            if not api.unlock(password):
                click.echo("Failed to unlock vault.", err=True)
                sys.exit(1)
        else:
            click.echo("Vault is locked. Use --unlock or --password.", err=True)
            sys.exit(1)

    cred = api.credential(name)

    if not cred:
        click.echo(f"Credential '{name}' not found.", err=True)
        sys.exit(1)

    if ctx.obj["json"]:
        click.echo(json.dumps(cred.to_dict(), indent=2))
    else:
        click.echo(f"Name:         {cred.name}")
        click.echo(f"Username:     {cred.username}")
        click.echo(f"Has Password: {cred.has_password}")
        click.echo(f"Has Key:      {cred.has_key}")
        click.echo(f"Is Default:   {cred.is_default}")
        click.echo(f"Jump Host:    {cred.jump_host or '(none)'}")
        click.echo(f"Match Hosts:  {', '.join(cred.match_hosts) or '(any)'}")
        click.echo(f"Match Tags:   {', '.join(cred.match_tags) or '(any)'}")


@cli.command("resolve")
@click.argument("hostname")
@click.option("-u", "--unlock", is_flag=True, help="Prompt for vault password")
@click.option("--password", default=None, help="Vault password")
@click.pass_context
def resolve_credential(ctx, hostname, unlock, password):
    """Find which credential would be used for a hostname."""
    api = get_api()

    # Handle vault unlock
    if not api.vault_unlocked:
        if unlock:
            password = getpass.getpass("Vault password: ")

        if password:
            if not api.unlock(password):
                click.echo("Failed to unlock vault.", err=True)
                sys.exit(1)
        else:
            click.echo("Vault is locked. Use --unlock or --password.", err=True)
            sys.exit(1)

    cred_name = api.resolve_credential(hostname)

    if ctx.obj["json"]:
        click.echo(json.dumps({"hostname": hostname, "credential": cred_name}))
    else:
        if cred_name:
            click.echo(f"{hostname} -> {cred_name}")
        else:
            click.echo(f"No matching credential for {hostname}")


@cli.command("status")
@click.pass_context
def show_status(ctx):
    """Show API status summary."""
    api = get_api()
    status = api.status()

    if ctx.obj["json"]:
        click.echo(json.dumps(status, indent=2))
    else:
        click.echo(f"Devices:           {status['devices']}")
        click.echo(f"Folders:           {status['folders']}")
        click.echo(f"Vault Initialized: {status['vault_initialized']}")
        click.echo(f"Vault Unlocked:    {status['vault_unlocked']}")
        if status['vault_unlocked']:
            click.echo(f"Credentials:       {status['credentials']}")


def main():
    """Entry point for CLI."""
    cli(obj={})


if __name__ == "__main__":
    main()