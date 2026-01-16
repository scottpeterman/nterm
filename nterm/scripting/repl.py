# nterm/scripting/repl.py
#
# A single "front door" that BOTH humans (GUI REPL) and MCP use.
# Guardrails live here, not in the agent.
#
# - Allow-list commands (or allow-list verbs + deny-list verbs)
# - Optional read-only mode
# - Session scoping (one device/session per REPL unless explicitly allowed)
# - Audit log of everything that ran

from __future__ import annotations

import json
import time
import shlex
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List

from .api import NTermAPI, ActiveSession, CommandResult
from .platform_utils import (
    get_platform_command,
    extract_version_info,
    extract_neighbor_info,
)


@dataclass
class REPLPolicy:
    mode: str = "read_only"  # "read_only" or "ops"
    max_output_chars: int = 250000
    max_command_seconds: int = 60

    # Simple and surprisingly effective "don't brick the network" guardrails
    deny_substrings: List[str] = field(default_factory=list)
    allow_prefixes: List[str] = field(default_factory=list)

    def is_allowed(self, command: str) -> bool:
        cmd = command.strip().lower()

        for bad in self.deny_substrings:
            if bad.lower() in cmd:
                return False

        if self.mode == "read_only":
            # Block common config verbs
            write_verbs = [
                "conf t",
                "configure",
                "copy ",
                "write",
                "wr ",
                "reload",
                "commit",
                "delete",
                "set ",
                "unset ",
                "clear ",
                "shutdown",
                "no shutdown",
                "format",
                "upgrade",
                "install",
            ]
            for verb in write_verbs:
                if cmd.startswith(verb):
                    return False

        # If allow_prefixes provided, require one of them
        if self.allow_prefixes:
            for pref in self.allow_prefixes:
                if cmd.startswith(pref.lower()):
                    return True
            return False

        return True


@dataclass
class REPLState:
    api: NTermAPI
    policy: REPLPolicy
    vault_unlocked: bool = False
    session: Optional[ActiveSession] = None
    connected_device: Optional[str] = None
    output_mode: str = "parsed"  # "raw" or "parsed"
    output_format: str = "text"  # "text", "rich", or "json" (for parsed mode only)
    platform_hint: Optional[str] = None  # Override platform for TextFSM
    debug_mode: bool = False  # Show full result data


class NTermREPL:
    """
    A minimal command router. This is the "tool surface".
    MCP can call `handle_line()`; humans can type into it.

    Meta Commands:
      :unlock              Unlock credential vault (prompts for password)
      :lock                Lock credential vault
      :creds [pattern]     List credentials
      :devices [pattern]   List devices
      :folders             List folders
      :connect <device>    Connect to device [--cred name] [--debug]
      :disconnect          Disconnect current session
      :disconnect_all      Disconnect all sessions
      :switch <device>     Switch to another active session
      :sessions            List all active sessions
      :policy [mode]       Get/set policy (read_only|ops)
      :mode [raw|parsed]   Get/set output mode
      :format [fmt]        Get/set format (text|rich|json)
      :set_hint <platform> Override platform detection
      :clear_hint          Use auto-detected platform
      :debug [on|off]      Toggle debug mode
      :dbinfo              Show TextFSM database info
      :help                Show help
      :exit                Disconnect and exit

    Quick Commands (platform-aware):
      :config              Fetch running config
      :version             Fetch and parse version info
      :interfaces          Fetch interface status
      :neighbors           Fetch CDP/LLDP neighbors (tries both)
      :bgp                 Fetch BGP summary
      :routes              Fetch routing table
      :intf <n>         Fetch specific interface details

    Raw Commands:
      (anything else)      Runs as CLI on the connected session
    """

    def __init__(self, api: Optional[NTermAPI] = None, policy: Optional[REPLPolicy] = None):
        if api is None:
            api = NTermAPI()
        if policy is None:
            policy = REPLPolicy(
                mode="read_only",
                deny_substrings=[
                    "terminal monitor",  # Don't want interactive spam
                ],
                allow_prefixes=[],
            )

        self.state = REPLState(api=api, policy=policy)

    def handle_line(self, line: str) -> Dict[str, Any]:
        line = (line or "").strip()
        if not line:
            return self._ok({"type": "noop"})

        if line.startswith(":"):
            return self._handle_meta(line)

        # Default: treat as CLI to send
        return self._handle_send(line)

    # -----------------------
    # Meta / REPL commands
    # -----------------------

    def _handle_meta(self, line: str) -> Dict[str, Any]:
        parts = shlex.split(line)
        cmd = parts[0].lower()

        # ===== Help & Exit =====
        if cmd == ":help":
            return self._ok({"type": "help", "text": self._help_text()})

        if cmd == ":exit":
            # Use disconnect_all for clean shutdown
            count = self.state.api.disconnect_all()
            self.state.session = None
            self.state.connected_device = None
            return self._ok({"type": "exit", "disconnected": count})

        # ===== Vault Commands =====
        if cmd == ":unlock":
            if len(parts) > 1:
                return self._err(":unlock takes no arguments. Password will be prompted securely.")
            return self._ok({"type": "unlock_prompt", "message": "Please provide vault password"})

        if cmd == ":lock":
            self.state.api.lock()
            self.state.vault_unlocked = False
            return self._ok({"type": "lock", "vault_unlocked": False})

        # ===== Inventory Commands =====
        if cmd == ":creds":
            if not self.state.api.vault_unlocked:
                return self._err("Vault is locked. Run :unlock first.")

            pattern = parts[1] if len(parts) >= 2 else None
            creds = self.state.api.credentials(pattern=pattern)
            rows = [c.to_dict() for c in creds]
            return self._ok({"type": "credentials", "credentials": rows})

        if cmd == ":devices":
            pattern = parts[1] if len(parts) >= 2 else None
            folder = None

            # Check for --folder flag
            for i, p in enumerate(parts):
                if p == "--folder" and i + 1 < len(parts):
                    folder = parts[i + 1]
                    break

            devs = self.state.api.devices(pattern=pattern, folder=folder)
            rows = [d.to_dict() for d in devs]
            return self._ok({"type": "devices", "devices": rows})

        if cmd == ":folders":
            folders = self.state.api.folders()
            return self._ok({"type": "folders", "folders": folders})

        # ===== Session Commands =====
        if cmd == ":connect":
            if len(parts) < 2:
                return self._err("Usage: :connect <device> [--cred name] [--debug]")

            device = parts[1]
            cred = None
            debug = self.state.debug_mode

            i = 2
            while i < len(parts):
                if parts[i] == "--cred" and i + 1 < len(parts):
                    cred = parts[i + 1]
                    i += 2
                elif parts[i] == "--debug":
                    debug = True
                    i += 1
                else:
                    i += 1

            if not self.state.api.vault_unlocked:
                return self._err("Vault is locked. Run :unlock first.")

            # Check if already connected to this device
            existing_sessions = self.state.api.active_sessions()
            for sess in existing_sessions:
                if sess.device_name == device:
                    # Already connected - just switch to it
                    self.state.session = sess
                    self.state.connected_device = sess.device_name
                    return self._ok({
                        "type": "switch",
                        "device": sess.device_name,
                        "hostname": sess.hostname,
                        "port": sess.port,
                        "platform": sess.platform,
                        "prompt": sess.prompt,
                        "message": "Already connected - switched to existing session",
                    })

            # NOTE: We no longer disconnect the existing session!
            # Old sessions stay active in the background.
            # User can switch back with :switch or disconnect with :disconnect

            try:
                sess = self.state.api.connect(device, credential=cred, debug=debug)
                self.state.session = sess
                self.state.connected_device = sess.device_name

                return self._ok({
                    "type": "connect",
                    "device": sess.device_name,
                    "hostname": sess.hostname,
                    "port": sess.port,
                    "platform": sess.platform,
                    "prompt": sess.prompt,
                })
            except Exception as e:
                return self._err(f"Connection failed: {e}")

        if cmd == ":disconnect":
            if not self.state.session:
                return self._ok({"type": "disconnect", "message": "No active session"})

            device_name = self.state.connected_device
            self._safe_disconnect()

            # Try to switch to another active session if available
            remaining = self.state.api.active_sessions()
            if remaining:
                self.state.session = remaining[0]
                self.state.connected_device = remaining[0].device_name
                return self._ok({
                    "type": "disconnect",
                    "disconnected": device_name,
                    "switched_to": self.state.connected_device,
                    "message": f"Disconnected {device_name}, switched to {self.state.connected_device}",
                })

            return self._ok({"type": "disconnect", "disconnected": device_name})

        if cmd == ":disconnect_all":
            count = self.state.api.disconnect_all()
            self.state.session = None
            self.state.connected_device = None
            return self._ok({"type": "disconnect_all", "count": count})

        if cmd == ":switch":
            if len(parts) < 2:
                # Show available sessions
                sessions = self.state.api.active_sessions()
                if not sessions:
                    return self._err("No active sessions. Use :connect <device> first.")

                session_names = [s.device_name for s in sessions]
                return self._err(f"Usage: :switch <device>\nActive sessions: {', '.join(session_names)}")

            target_device = parts[1]

            # Find the session
            sessions = self.state.api.active_sessions()
            for sess in sessions:
                if sess.device_name == target_device:
                    self.state.session = sess
                    self.state.connected_device = sess.device_name
                    return self._ok({
                        "type": "switch",
                        "device": sess.device_name,
                        "hostname": sess.hostname,
                        "port": sess.port,
                        "platform": sess.platform,
                        "prompt": sess.prompt,
                    })

            # Not found
            session_names = [s.device_name for s in sessions]
            return self._err(f"Session '{target_device}' not found.\nActive sessions: {', '.join(session_names)}")

        if cmd == ":sessions":
            sessions = self.state.api.active_sessions()
            rows = []
            for s in sessions:
                rows.append({
                    "device": s.device_name,
                    "hostname": s.hostname,
                    "port": s.port,
                    "platform": s.platform,
                    "prompt": s.prompt,
                    "connected": s.is_connected(),
                })
            return self._ok({
                "type": "sessions",
                "sessions": rows,
                "current": self.state.connected_device,
            })

        # ===== Settings Commands =====
        if cmd == ":policy":
            if len(parts) < 2:
                return self._ok({"type": "policy", "mode": self.state.policy.mode})
            mode = parts[1].lower()
            if mode not in ["read_only", "ops"]:
                return self._err("Policy must be read_only or ops")
            self.state.policy.mode = mode
            return self._ok({"type": "policy", "mode": mode})

        if cmd == ":mode":
            if len(parts) < 2:
                return self._ok({
                    "type": "mode",
                    "mode": self.state.output_mode,
                    "platform_hint": self.state.platform_hint,
                })
            mode = parts[1].lower()
            if mode not in ["raw", "parsed"]:
                return self._err("Mode must be raw or parsed")
            self.state.output_mode = mode
            return self._ok({"type": "mode", "mode": mode})

        if cmd == ":format":
            if len(parts) < 2:
                return self._ok({"type": "format", "format": self.state.output_format})
            fmt = parts[1].lower()
            if fmt not in ["text", "rich", "json"]:
                return self._err("Format must be text, rich, or json")
            self.state.output_format = fmt
            return self._ok({"type": "format", "format": fmt})

        if cmd == ":set_hint":
            if len(parts) < 2:
                return self._err("Usage: :set_hint <platform> (e.g., cisco_ios, arista_eos)")
            self.state.platform_hint = parts[1]
            return self._ok({"type": "set_hint", "platform_hint": self.state.platform_hint})

        if cmd == ":clear_hint":
            self.state.platform_hint = None
            return self._ok({"type": "clear_hint"})

        if cmd == ":debug":
            if len(parts) < 2:
                return self._ok({"type": "debug", "debug_mode": self.state.debug_mode})
            val = parts[1].lower()
            self.state.debug_mode = val in ["on", "true", "1", "yes"]
            return self._ok({"type": "debug", "debug_mode": self.state.debug_mode})

        if cmd == ":dbinfo":
            info = self.state.api.db_info()
            return self._ok({"type": "dbinfo", "db_info": info})

        # ===== Quick Commands =====
        if cmd == ":config":
            return self._quick_config()

        if cmd == ":version":
            return self._quick_version()

        if cmd == ":interfaces":
            return self._quick_interfaces()

        if cmd == ":neighbors":
            return self._quick_neighbors()

        if cmd == ":bgp":
            return self._quick_bgp()

        if cmd == ":routes":
            return self._quick_routes()

        if cmd == ":intf":
            if len(parts) < 2:
                return self._err("Usage: :intf <interface> (e.g., :intf Gi0/1)")
            return self._quick_interface_detail(parts[1])

        return self._err(f"Unknown REPL command: {cmd}")

    # -----------------------
    # Quick commands
    # -----------------------

    def _quick_config(self) -> Dict[str, Any]:
        """Fetch running configuration."""
        if not self.state.session:
            return self._err("Not connected. Use :connect <device>")

        try:
            started = time.time()
            result = self.state.api.send_platform_command(
                self.state.session,
                'config',
                parse=False,  # Config is typically not parsed
                timeout=60,
            )
            elapsed = time.time() - started

            if not result:
                return self._err("Config command not available for this platform")

            payload = result.to_dict()
            payload["elapsed_seconds"] = round(elapsed, 3)
            payload["command_type"] = "config"

            return self._ok({"type": "config", "result": payload})

        except Exception as e:
            return self._err(f"Config fetch failed: {e}")

    def _quick_version(self) -> Dict[str, Any]:
        """Fetch and extract version info."""
        if not self.state.session:
            return self._err("Not connected. Use :connect <device>")

        try:
            started = time.time()
            result = self.state.api.send_platform_command(
                self.state.session,
                'version',
                parse=True,
                timeout=30,
            )
            elapsed = time.time() - started

            if not result:
                return self._err("Version command not available for this platform")

            # Extract structured version info
            version_info = extract_version_info(
                result.parsed_data,
                self.state.platform_hint or self.state.session.platform
            )

            payload = result.to_dict()
            payload["elapsed_seconds"] = round(elapsed, 3)
            payload["command_type"] = "version"
            payload["version_info"] = version_info

            return self._ok({"type": "version", "result": payload})

        except Exception as e:
            return self._err(f"Version command failed: {e}")

    def _quick_interfaces(self) -> Dict[str, Any]:
        """Fetch interface status."""
        if not self.state.session:
            return self._err("Not connected. Use :connect <device>")

        try:
            started = time.time()
            result = self.state.api.send_platform_command(
                self.state.session,
                'interfaces_status',
                parse=True,
                timeout=30,
            )
            elapsed = time.time() - started

            if not result:
                return self._err("Interfaces command not available for this platform")

            payload = result.to_dict()
            payload["elapsed_seconds"] = round(elapsed, 3)
            payload["command_type"] = "interfaces"

            return self._ok({"type": "interfaces", "result": payload})

        except Exception as e:
            return self._err(f"Interfaces command failed: {e}")

    def _quick_neighbors(self) -> Dict[str, Any]:
        """Fetch CDP/LLDP neighbors with fallback."""
        if not self.state.session:
            return self._err("Not connected. Use :connect <device>")

        platform = self.state.platform_hint or self.state.session.platform

        # Build command list - CDP first for Cisco, LLDP first for others
        cdp_cmd = get_platform_command(platform, 'neighbors_cdp')
        lldp_cmd = get_platform_command(platform, 'neighbors_lldp')

        if platform and 'cisco' in platform:
            commands = [cdp_cmd, lldp_cmd]
        else:
            commands = [lldp_cmd, cdp_cmd]

        # Filter None commands
        commands = [c for c in commands if c]

        if not commands:
            return self._err(f"No neighbor discovery commands available for platform '{platform}'")

        try:
            started = time.time()
            result = self.state.api.send_first(
                self.state.session,
                commands,
                parse=True,
                timeout=30,
                require_parsed=True,
            )
            elapsed = time.time() - started

            if not result:
                # Try without requiring parsed data
                result = self.state.api.send_first(
                    self.state.session,
                    commands,
                    parse=True,
                    timeout=30,
                    require_parsed=False,
                )

            if not result:
                return self._ok({
                    "type": "neighbors",
                    "result": {
                        "command": "CDP/LLDP",
                        "raw_output": "No neighbors found or commands failed",
                        "parsed_data": [],
                        "elapsed_seconds": round(elapsed, 3),
                    }
                })

            # Extract normalized neighbor info
            neighbors = extract_neighbor_info(result.parsed_data) if result.parsed_data else []

            payload = result.to_dict()
            payload["elapsed_seconds"] = round(elapsed, 3)
            payload["command_type"] = "neighbors"
            payload["neighbor_info"] = neighbors

            return self._ok({"type": "neighbors", "result": payload})

        except Exception as e:
            return self._err(f"Neighbor discovery failed: {e}")

    def _quick_bgp(self) -> Dict[str, Any]:
        """Fetch BGP summary."""
        if not self.state.session:
            return self._err("Not connected. Use :connect <device>")

        try:
            started = time.time()
            result = self.state.api.send_platform_command(
                self.state.session,
                'bgp_summary',
                parse=True,
                timeout=30,
            )
            elapsed = time.time() - started

            if not result:
                return self._err("BGP command not available for this platform")

            payload = result.to_dict()
            payload["elapsed_seconds"] = round(elapsed, 3)
            payload["command_type"] = "bgp"

            return self._ok({"type": "bgp", "result": payload})

        except Exception as e:
            return self._err(f"BGP command failed: {e}")

    def _quick_routes(self) -> Dict[str, Any]:
        """Fetch routing table."""
        if not self.state.session:
            return self._err("Not connected. Use :connect <device>")

        try:
            started = time.time()
            result = self.state.api.send_platform_command(
                self.state.session,
                'routing_table',
                parse=True,
                timeout=30,
            )
            elapsed = time.time() - started

            if not result:
                return self._err("Routing command not available for this platform")

            payload = result.to_dict()
            payload["elapsed_seconds"] = round(elapsed, 3)
            payload["command_type"] = "routes"

            return self._ok({"type": "routes", "result": payload})

        except Exception as e:
            return self._err(f"Routing command failed: {e}")

    def _quick_interface_detail(self, interface: str) -> Dict[str, Any]:
        """Fetch specific interface details."""
        if not self.state.session:
            return self._err("Not connected. Use :connect <device>")

        try:
            started = time.time()
            result = self.state.api.send_platform_command(
                self.state.session,
                'interface_detail',
                name=interface,
                parse=True,
                timeout=30,
            )
            elapsed = time.time() - started

            if not result:
                return self._err(f"Interface detail command not available for this platform")

            payload = result.to_dict()
            payload["elapsed_seconds"] = round(elapsed, 3)
            payload["command_type"] = "interface_detail"
            payload["interface"] = interface

            return self._ok({"type": "interface_detail", "result": payload})

        except Exception as e:
            return self._err(f"Interface detail command failed: {e}")

    # -----------------------
    # CLI send path
    # -----------------------

    def _handle_send(self, cli: str) -> Dict[str, Any]:
        if not self.state.session:
            return self._err("Not connected. Use :connect <device>")

        if not self.state.policy.is_allowed(cli):
            return self._err(f"Blocked by policy ({self.state.policy.mode}): {cli}")

        try:
            started = time.time()

            # Determine if we should parse based on output mode
            should_parse = (self.state.output_mode == "parsed")

            # Apply platform hint if set
            original_platform = self.state.session.platform
            if self.state.platform_hint:
                self.state.session.platform = self.state.platform_hint

            try:
                res: CommandResult = self.state.api.send(
                    self.state.session,
                    cli,
                    timeout=self.state.policy.max_command_seconds,
                    parse=should_parse,
                    normalize=True,
                )
            finally:
                # Restore original platform
                if self.state.platform_hint:
                    self.state.session.platform = original_platform

            elapsed = time.time() - started

            # Clip raw output for safety/transport
            raw = res.raw_output or ""
            if len(raw) > self.state.policy.max_output_chars:
                raw = raw[:self.state.policy.max_output_chars] + "\n...<truncated>..."

            payload = res.to_dict()
            payload["raw_output"] = raw
            payload["elapsed_seconds"] = round(elapsed, 3)

            return self._ok({"type": "result", "result": payload})
        except Exception as e:
            return self._err(f"Command execution failed: {e}")

    # -----------------------
    # Helpers
    # -----------------------

    def _safe_disconnect(self) -> None:
        """Disconnect current session only (not all sessions)."""
        if self.state.session:
            try:
                self.state.api.disconnect(self.state.session)
            finally:
                self.state.session = None
                self.state.connected_device = None

    def do_unlock(self, password: str) -> Dict[str, Any]:
        """Internal method to perform unlock with password."""
        try:
            ok = self.state.api.unlock(password)
            self.state.vault_unlocked = bool(ok)
            return self._ok({"type": "unlock", "vault_unlocked": self.state.vault_unlocked})
        except Exception as e:
            return self._err(f"Unlock failed: {e}")

    def _help_text(self) -> str:
        return """
nterm REPL Commands
===================

Vault:
  :unlock              Unlock credential vault (prompts securely)
  :lock                Lock credential vault

Inventory:
  :creds [pattern]     List credentials (supports glob patterns)
  :devices [pattern]   List devices [--folder name]
  :folders             List all folders

Sessions:
  :connect <device>    Connect to device [--cred name] [--debug]
  :disconnect          Disconnect current session
  :disconnect_all      Disconnect all sessions
  :switch <device>     Switch to another active session
  :sessions            List all active sessions

Quick Commands (platform-aware, auto-selects correct syntax):
  :config              Fetch running configuration
  :version             Fetch and parse version info
  :interfaces          Fetch interface status
  :neighbors           Fetch CDP/LLDP neighbors (tries both)
  :bgp                 Fetch BGP summary
  :routes              Fetch routing table
  :intf <n>            Fetch specific interface details

Settings:
  :policy [mode]       Get/set policy mode (read_only|ops)
  :mode [raw|parsed]   Get/set output mode
  :format [fmt]        Get/set display format (text|rich|json)
  :set_hint <platform> Override platform detection (cisco_ios, arista_eos, etc.)
  :clear_hint          Use auto-detected platform
  :debug [on|off]      Toggle debug mode

Info:
  :dbinfo              Show TextFSM database status
  :help                Show this help
  :exit                Disconnect all and exit

Raw Commands:
  (anything else)      Sends as CLI command to connected device

Multi-Session Example:
  :connect spine-1     # Connect to first device
  show version         # Run command on spine-1
  :connect spine-2     # Connect to second (spine-1 stays active!)
  show version         # Run command on spine-2
  :sessions            # See both sessions
  :switch spine-1      # Switch back to spine-1
  show ip route        # Run command on spine-1
  :disconnect          # Disconnect spine-1, auto-switch to spine-2
  :disconnect_all      # Disconnect all remaining sessions
  :exit
"""

    def _ok(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {"ok": True, "data": data, "ts": datetime.now().isoformat()}

    def _err(self, message: str) -> Dict[str, Any]:
        return {"ok": False, "error": message, "ts": datetime.now().isoformat()}