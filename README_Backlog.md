# nterm MVP Backlog

Version 1.0 shipped — tracking issues and features for v1.1+

---

## ✅ Completed

### Tab Close Warning (P0) — Done
- ~~Closing a tab with active SSH connection just closes silently~~
- Modal confirmation: "Session active. Disconnect and close?"

### App Close Warning (P0) — Done
- ~~Closing app with multiple active sessions — no warning~~
- "You have N active sessions. Close all and quit?"

### Tab Reordering (P1) — Done
- ~~Cannot drag tabs to rearrange~~
- Was already implemented: `QTabBar.setMovable(True)`

### Close All Tabs (P1) — Done
- File → Close All Tabs (`Ctrl+Shift+W`)
- Prompts if any sessions active

### Close Other Tabs — Done (Bonus)
- Right-click tab → Close Others
- Right-click tab → Close Tabs to Right

### Close Current Tab Shortcut — Done (Bonus)
- `Ctrl+W` closes current tab with warning

### Pop-out Window Close Warning — Done (Bonus)
- Standalone terminal windows now warn before closing active sessions

---

## P1: Session Logging

Network engineers need audit trails.

### Record Session to File
- **Issue**: No way to capture session output to log file
- **Expected**: Per-session toggle or connection profile option
- **Options**:
  - Raw output (with ANSI escapes)
  - Stripped plaintext
  - Timestamped format: `[2025-01-11 14:32:01] show ip route`
- **UI**: Session menu → "Start Recording..." / "Stop Recording"
- **Profile option**: `log_file: ~/logs/{hostname}_{timestamp}.log`
- **Scope**: Tap the PTY output stream before terminal rendering

---

## P1: Connection Crypto Profiles

### Per-Profile Crypto Settings
- **Issue**: Auto-fallback for legacy devices is slow and opaque
- **Expected**: Explicit crypto config per connection profile
- **Benefit**: Faster connections, predictable behavior, security compliance

### Profile Schema Addition

```yaml
# connection-profiles.yaml
profiles:
  - name: "core-router"
    hostname: "core-rtr01.network.corp"
    username: "admin"
    credential_pattern: "network-*"
    
    # NEW: Explicit crypto settings
    crypto:
      preset: "legacy-cisco"  # or "modern", "paranoid", "custom"
      
  - name: "old-juniper"
    hostname: "192.168.1.50"
    crypto:
      preset: "custom"
      kex:
        - "diffie-hellman-group14-sha256"
        - "diffie-hellman-group14-sha1"
        - "diffie-hellman-group1-sha1"
      ciphers:
        - "aes128-ctr"
        - "aes128-cbc"
        - "3des-cbc"
      macs:
        - "hmac-sha2-256"
        - "hmac-sha1"
      host_key_algorithms:
        - "rsa-sha2-256"
        - "ssh-rsa"
      # Force RSA SHA-1 for ancient OpenSSH
      allow_rsa_sha1: true
      # Disable strict host key checking for lab gear
      strict_host_key: false
```

### Built-in Presets

| Preset | Use Case | KEX | Ciphers |
|--------|----------|-----|---------|
| `modern` | Default, OpenSSH 7.2+ | curve25519, ecdh-sha2-* | chacha20, aes256-gcm |
| `compatible` | Most network gear | group14-sha256, group14-sha1 | aes128-ctr, aes128-cbc |
| `legacy-cisco` | IOS 12.x, old ASA | group14-sha1, group1-sha1 | aes128-cbc, 3des-cbc |
| `legacy-juniper` | Junos 14.x and earlier | group14-sha1 | aes128-cbc |
| `paranoid` | Security-hardened | curve25519 only | chacha20-poly1305 only |

### UI Integration

**Connection Dialog**:
```
┌─ Crypto Settings ─────────────────────────┐
│ Preset: [Compatible ▼]                    │
│                                           │
│ ☐ Customize...                            │
│   KEX:     [group14-sha256, group14-sha1] │
│   Ciphers: [aes128-ctr, aes128-cbc      ] │
│   MACs:    [hmac-sha2-256, hmac-sha1    ] │
│                                           │
│ ☑ Allow RSA SHA-1 signatures              │
│ ☐ Disable strict host key checking        │
└───────────────────────────────────────────┘
```

### Scope Considerations

- **Phase 1**: Presets only (dropdown in connection dialog)
- **Phase 2**: Custom algorithm lists (power user UI)
- **Phase 3**: Auto-detect and remember (connect, probe, save working config)

---

## P1: Distribution

### PyInstaller Builds
- **Platforms**: Windows x64, macOS (Intel + ARM), Linux x64
- **Challenges**:
  - PyQt6 + WebEngine is heavy (~150MB+)
  - xterm.js assets need bundled
  - Keyring backends vary by platform
- **Deliverables**:
  - Windows: `.exe` installer or portable zip
  - macOS: `.app` bundle (maybe `.dmg`)
  - Linux: AppImage or portable tarball
- **CI**: GitHub Actions workflow for release builds

---

## P2: Per-Session Themes

### Individual Tab Theming
- **Issue**: Theme is global — can't visually distinguish prod vs lab
- **Expected**: Right-click tab → "Set Theme..." or in connection profile
- **Use case**: Red theme for production, green for lab, default for dev
- **Profile option**: `theme: gruvbox_dark`
- **Scope**: Each `TerminalWidget` already has `set_theme()` — need UI wiring

---

## P2: Multi-Tab Commands

### Broadcast Mode
- **Issue**: No way to run same command across multiple sessions
- **Expected**: 
  - Select tabs (checkboxes or Ctrl+click)
  - Input goes to all selected
  - Or: dedicated "Broadcast" input bar
- **Safety**: Confirmation before enabling ("Commands will be sent to N sessions")
- **Visual**: Indicate broadcast-active tabs (colored border or icon)

---

## P2: In-App Help

### Help System
- **Issue**: No documentation accessible from the app
- **Options**:
  - Help menu → opens GitHub README/wiki
  - Built-in quick reference dialog (keyboard shortcuts, features)
  - Tooltips on connection dialog fields
- **Minimum**: Help → "Keyboard Shortcuts" modal
- **Shortcuts to document**:
  - `Ctrl+N` — Quick Connect
  - `Ctrl+W` — Close tab
  - `Ctrl+Shift+W` — Close all tabs
  - `Ctrl+Shift+C` — Credential Manager
  - `Ctrl+,` — Settings
  - `Ctrl+I` — Import sessions
  - `Ctrl+E` — Export sessions

---

## P3: Nice to Have (Post-MVP)

- **Session state persistence** — Reopen app with previous tabs
- **Tab pinning** — Pinned tabs can't be accidentally closed
- **Command history across sessions** — Searchable
- **Connection profile import/export** — Bulk device management
- **Quick connect** — `Ctrl+K` → type hostname → connect with default creds
- **Split panes** — Horizontal/vertical split within tab

---

## Implementation Order (Revised)

```
Week 1: ✅ DONE
├── Tab close warning (P0) ✅
├── App close warning (P0) ✅
├── Tab reordering (P1) ✅
├── Close All Tabs (P1) ✅
├── Tab context menu (bonus) ✅
└── Window close warning (bonus) ✅

Week 2: Session Logging
└── Record to file (P1) — high value for network eng workflows

Week 3: Crypto Profiles
├── CryptoConfig dataclass + presets (P1)
├── Connection dialog dropdown (P1)
└── Profile YAML schema update (P1)

Week 4: Distribution
└── PyInstaller builds (P1) — unlocks non-dev users

Week 5: Polish
├── Per-session themes (P2)
├── Help/shortcuts modal (P2)
├── Custom crypto UI (P2) — phase 2 of crypto profiles
└── Broadcast mode (P2) — scope carefully, can be complex
```

---

## Notes

- ~~Tab management fixes are mostly Qt boilerplate — fast wins~~ ✅ Done
- Session logging architecture matters: design for future features (search, replay)
- Broadcast mode is powerful but dangerous — invest in safety UX
- PyInstaller will surface hidden dependencies — budget debug time

---

## Changelog

**2025-01-11**: Completed all P0 session safety and P1 tab management items
- Tab close confirmation for active sessions
- App quit confirmation with session count
- Tab context menu (Close, Close Others, Close to Right, Close All)
- `Ctrl+W` / `Ctrl+Shift+W` shortcuts
- Pop-out window close warnings