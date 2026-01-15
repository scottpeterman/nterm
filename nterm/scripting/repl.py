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

import os
import json
import time
import shlex
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List

from .api import NTermAPI, ActiveSession, CommandResult


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

        i = 0
        while i < len(self.deny_substrings):
            bad = self.deny_substrings[i].lower()
            if bad in cmd:
                return False
            i += 1

        if self.mode == "read_only":
            # Cheap "write reminder": block common config verbs
            # (You can tighten to an allow-list only if you want)
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
            j = 0
            while j < len(write_verbs):
                if cmd.startswith(write_verbs[j]):
                    return False
                j += 1

        # If allow_prefixes provided, require one of them
        if self.allow_prefixes:
            ok = False
            k = 0
            while k < len(self.allow_prefixes):
                pref = self.allow_prefixes[k].lower()
                if cmd.startswith(pref):
                    ok = True
                    break
                k += 1
            return ok

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

    Commands:
      :unlock
      :lock
      :creds [pattern]
      :devices [pattern]
      :connect <device> [--cred name]
      :disconnect
      :policy [read_only|ops]
      :mode [raw|parsed]
      :format [text|rich|json]
      :set_hint <platform>
      :clear_hint
      :debug [on|off]
      :dbinfo
      (anything else runs as CLI on the connected session)
      :help
      :exit
    """

    def __init__(self, api: Optional[NTermAPI] = None, policy: Optional[REPLPolicy] = None):
        if api is None:
            api = NTermAPI()
        if policy is None:
            policy = REPLPolicy(
                mode="read_only",
                deny_substrings=[
                    "terminal monitor",  # example if you don't want interactive spam
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

        if cmd == ":help":
            return self._ok({"type": "help", "text": self._help_text()})

        if cmd == ":exit":
            if self.state.session:
                self._safe_disconnect()
            return self._ok({"type": "exit"})

        if cmd == ":unlock":
            # Password should be provided separately, not in the command line
            if len(parts) > 1:
                return self._err(":unlock takes no arguments. Password will be prompted securely.")
            return self._ok({"type": "unlock_prompt", "message": "Please provide vault password"})

        if cmd == ":lock":
            self.state.api.lock()
            self.state.vault_unlocked = False
            return self._ok({"type": "lock", "vault_unlocked": False})

        if cmd == ":creds":
            if not self.state.api.vault_unlocked:
                return self._err("Vault is locked. Run :unlock <password> first.")

            pattern = None
            if len(parts) >= 2:
                pattern = parts[1]

            creds = self.state.api.credentials(pattern=pattern)
            rows: List[Dict[str, Any]] = []
            i = 0
            while i < len(creds):
                rows.append(creds[i].to_dict())
                i += 1
            return self._ok({"type": "credentials", "credentials": rows})

        if cmd == ":devices":
            pattern = None
            if len(parts) >= 2:
                pattern = parts[1]
            devs = self.state.api.devices(pattern=pattern)
            # No comprehensions
            rows: List[Dict[str, Any]] = []
            i = 0
            while i < len(devs):
                rows.append(devs[i].to_dict())
                i += 1
            return self._ok({"type": "devices", "devices": rows})

        if cmd == ":connect":
            if len(parts) < 2:
                return self._err("Usage: :connect <device> [--cred name]")

            device = parts[1]
            cred = None

            i = 2
            while i < len(parts):
                if parts[i] == "--cred":
                    if i + 1 < len(parts):
                        cred = parts[i + 1]
                        i += 1
                i += 1

            if not self.state.api.vault_unlocked:
                return self._err("Vault is locked. Run :unlock <password> first.")

            if self.state.session:
                self._safe_disconnect()

            try:
                # Pass debug flag from REPL state
                sess = self.state.api.connect(
                    device,
                    credential=cred,
                    debug=self.state.debug_mode  # <-- This line
                )
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
            self._safe_disconnect()
            return self._ok({"type": "disconnect"})

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
                return self._err("Mode must be 'raw' or 'parsed'")
            self.state.output_mode = mode
            return self._ok({"type": "mode", "mode": mode})

        if cmd == ":format":
            if len(parts) < 2:
                return self._ok({
                    "type": "format",
                    "format": self.state.output_format,
                })
            fmt = parts[1].lower()
            if fmt not in ["text", "rich", "json"]:
                return self._err("Format must be 'text', 'rich', or 'json'")
            self.state.output_format = fmt
            return self._ok({"type": "format", "format": fmt})

        if cmd == ":set_hint":
            if len(parts) < 2:
                return self._err("Usage: :set_hint <platform> (e.g., cisco_ios, arista_eos)")
            platform = parts[1].lower()
            self.state.platform_hint = platform
            return self._ok({"type": "set_hint", "platform_hint": platform})

        if cmd == ":clear_hint":
            self.state.platform_hint = None
            return self._ok({"type": "clear_hint"})

        if cmd == ":debug":
            if len(parts) >= 2:
                mode = parts[1].lower()
                if mode in ["on", "true", "1"]:
                    self.state.debug_mode = True
                elif mode in ["off", "false", "0"]:
                    self.state.debug_mode = False
                else:
                    return self._err("Debug mode must be on or off")
            else:
                # Toggle
                self.state.debug_mode = not self.state.debug_mode
            return self._ok({"type": "debug", "debug_mode": self.state.debug_mode})

        if cmd == ":dbinfo":
            try:
                db_info = self.state.api.db_info()
                return self._ok({"type": "dbinfo", "db_info": db_info})
            except Exception as e:
                return self._err(f"Failed to get DB info: {e}")

        return self._err(f"Unknown REPL command: {cmd}")

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
            
            # Apply platform hint if set (modify session platform temporarily)
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
                raw = raw[: self.state.policy.max_output_chars] + "\n...<truncated>..."

            payload = res.to_dict()
            payload["raw_output"] = raw
            payload["elapsed_seconds"] = round(elapsed, 3)

            return self._ok({"type": "result", "result": payload})
        except Exception as e:
            return self._err(f"Command execution failed: {e}")

    def _safe_disconnect(self) -> None:
        if self.state.session:
            try:
                self.state.api.disconnect(self.state.session)
            finally:
                self.state.session = None
                self.connected_device = None

    def do_unlock(self, password: str) -> Dict[str, Any]:
        """Internal method to perform unlock with password."""
        try:
            ok = self.state.api.unlock(password)
            self.state.vault_unlocked = bool(ok)
            return self._ok({"type": "unlock", "vault_unlocked": self.state.vault_unlocked})
        except Exception as e:
            return self._err(f"Unlock failed: {e}")

    def _help_text(self) -> str:
        return (
            "Commands:\n"
            "  :unlock             (prompts for vault password securely)\n"
            "  :lock\n"
            "  :creds [pattern]\n"
            "  :devices [pattern]\n"
            "  :connect <device> [--cred name]\n"
            "  :disconnect\n"
            "  :policy [read_only|ops]\n"
            "  :mode [raw|parsed]  (control output format, default: parsed)\n"
            "  :format [text|rich|json] (parsed mode display format, default: text)\n"
            "  :set_hint <platform> (override TextFSM platform, e.g., cisco_ios)\n"
            "  :clear_hint         (use auto-detected platform)\n"
            "  :debug [on|off]     (show full result data for troubleshooting)\n"
            "  :dbinfo             (show TextFSM database status)\n"
            "  (anything else runs as CLI on the connected session)\n"
            "  :help\n"
            "  :exit\n"
        )

    def _ok(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {"ok": True, "data": data, "ts": datetime.now().isoformat()}

    def _err(self, message: str) -> Dict[str, Any]:
        return {"ok": False, "error": message, "ts": datetime.now().isoformat()}