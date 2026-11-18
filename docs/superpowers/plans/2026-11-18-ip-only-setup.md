# IP-only Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the plugin configurable with only the PC's IP address, learning its MAC from the ARP table, and replace required text entry with a gamepad keypad.

**Architecture:** The Python backend owns config schema v2, MAC resolution, and wake; the React frontend shows an IP-first settings view whose only input is a custom `KeypadModal` built from `@decky/ui` buttons. Existing LAN discovery stays as the alternative setup path.

**Tech Stack:** Python 3.11 + pytest (`asyncio_mode = "auto"`), React 18 + TypeScript, `@decky/api`, `@decky/ui`, pnpm + rollup.

**Spec:** `docs/superpowers/specs/2026-11-18-ip-only-setup-design.md`

## Global Constraints

- Schema version 2. v1 configs load and migrate; corrupt configs still back up and reset.
- `ip` is the only required field. `mac` may be empty. `broadcast` empty means derive `/24` from `ip`.
- MAC is resolved with a ping to prime ARP, then `/proc/net/arp`, then `ip neigh`; match the exact IP.
- No `TextField` for required values. IP, MAC, broadcast and port use `KeypadModal`.
- Message when MAC cannot be learned: `MAC address unknown. Turn the PC on once, save again, or use Discover.`
- Wake rate limit (3 s), 120 s timeout, polling (2 s waking / 5 s idle), packet format and fan-out are unchanged.
- All new UI strings and labels exactly as written in this plan and the spec.

## Review Focus

1. PC off, MAC never learned: Wake must return `mac_unknown` with that message and send nothing — no crash, no false "sent".
2. Upgrading with an existing v1 config: MAC, broadcast and probe port must survive, not reset.
3. Saving an IP while the PC is off: save succeeds, no MAC is stored, and the UI says the PC must be on once.
4. Keypad accepts only the configured characters and length; `999.1.1.1` must be rejected on save with an inline error.
5. Cancel on the keypad discards the edit and leaves the previous value.

---

### Task 1: Backend config schema v2 (IP required, MAC optional)

**WDD class:** wiring

**Files:**
- Modify: `main.py` (Config/`SCHEMA_VERSION`/`validate_config`/`load_config`, near lines 18–97)
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `SCHEMA_VERSION = 2`; `SUPPORTED_SCHEMA_VERSIONS = (1, 2)`; `validate_config(d: dict) -> Config` accepting `{"ip": "192.168.1.42"}` and returning `Config(mac="", broadcast="192.168.1.255")`; `load_config()` migrating v1 without resetting.
- Produces: reuse `derive_subnet_broadcast(ip)` as the broadcast derivation.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_config.py`:

```python
def test_ip_only_config_derives_broadcast():
    cfg = validate_config({"ip": "192.168.1.42"})
    assert cfg.mac == ""
    assert cfg.broadcast == "192.168.1.255"
    assert cfg.alias == "My PC"

def test_ip_required():
    with pytest.raises(ValueError):
        validate_config({"alias": "x"})

def test_v1_config_migrates(tmp_path, monkeypatch):
    import main
    monkeypatch.setenv("DECKY_PLUGIN_SETTINGS_DIR", str(tmp_path))
    main.SETTINGS_DIR = tmp_path
    (tmp_path / "config.json").write_text(json.dumps({
        "schema_version": 1, "alias": "Gaming PC",
        "mac": "aa:bb:cc:dd:ee:ff", "ip": "192.168.1.42",
        "broadcast": "255.255.255.255", "probe_port": 445,
    }))
    cfg = load_config()
    assert cfg.mac == "aa:bb:cc:dd:ee:ff"
    assert cfg.probe_port == 445
    assert json.loads((tmp_path / "config.json").read_text())["schema_version"] == 2
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_config.py -q`
Expected: FAIL — `schema mismatch` reset or missing broadcast.

- [ ] **Step 3: Implement schema v2 in `main.py`**

Set `SCHEMA_VERSION = 2` and `SUPPORTED_SCHEMA_VERSIONS = (1, 2)`. In `validate_config`, require and validate `ip`, normalize `mac` only when `str(d.get("mac", "")).strip()` is non-empty, and set `broadcast = _validate_ip(str(d.get("broadcast") or derive_subnet_broadcast(ip) or "255.255.255.255"))`. In `load_config`, raise on versions outside `SUPPORTED_SCHEMA_VERSIONS`, validate the data, and call `save_config(cfg)` when the stored version differs from `SCHEMA_VERSION`.

- [ ] **Step 4: Run the full backend suite**

Run: `python -m pytest -q`
Expected: all pass (update `test_preflight` only if the MAC change requires it; `preflight` still mentions MAC when empty).

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_config.py
git commit -m "feat: schema v2 config requires only the PC IP"
```

---

### Task 2: Learn the MAC from the IP and use it in wake

**WDD class:** dense

**Files:**
- Modify: `main.py` (`_parse_arp_table` area ~line 214; `wake` ~line 116; `Plugin` ~line 299)
- Test: `tests/test_resolve.py` (create)

**Interfaces:**
- Produces: `_find_mac_in_arp(text: str, ip: str) -> str | None`; `_find_mac_in_neigh(text: str, ip: str) -> str | None`; `async def resolve_mac(ip: str) -> str | None`; `Plugin.learn_mac() -> {"mac": str | None}`; `Plugin.save_config(data) -> {"ok": True, "config": dict, "mac_resolved": bool}`.
- Consumes: `Config`, `load_config`, `save_config`, `SCHEMA_VERSION` from Task 1.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_resolve.py`:

```python
import pytest
from unittest import mock
from main import _find_mac_in_arp, _find_mac_in_neigh, resolve_mac, wake, Config

ARP = """IP address       HW type     Flags       HW address            Mask
192.168.1.42     0x1         0x2         aa:bb:cc:dd:ee:ff     *
192.168.1.43     0x1         0x2         11:22:33:44:55:66     *"""

NEIGH = """192.168.1.42 dev wlan0 lladdr aa:bb:cc:dd:ee:ff REACHABLE
192.168.1.43 dev wlan0 lladdr 11:22:33:44:55:66 STALE"""

def test_find_mac_in_arp_exact_ip():
    assert _find_mac_in_arp(ARP, "192.168.1.42") == "aa:bb:cc:dd:ee:ff"
    assert _find_mac_in_arp(ARP, "192.168.1.99") is None

def test_find_mac_in_neigh_exact_ip():
    assert _find_mac_in_neigh(NEIGH, "192.168.1.42") == "aa:bb:cc:dd:ee:ff"
    assert _find_mac_in_neigh(NEIGH, "192.168.1.99") is None

@pytest.mark.asyncio
async def test_resolve_mac_reads_arp(tmp_path, monkeypatch):
    import main
    arp = tmp_path / "arp"
    arp.write_text(ARP)
    async def no_ping(*a, **k):
        raise OSError("no ping")
    monkeypatch.setattr(main, "_ARP_PATH", arp)
    with mock.patch("asyncio.create_subprocess_exec", side_effect=no_ping):
        assert await resolve_mac("192.168.1.42") == "aa:bb:cc:dd:ee:ff"

@pytest.mark.asyncio
async def test_wake_without_mac_returns_mac_unknown(monkeypatch):
    import main
    async def none(ip): return None
    monkeypatch.setattr(main, "resolve_mac", none)
    res = await wake(Config(ip="192.168.1.42", broadcast="192.168.1.255"))
    assert res["error"] == "mac_unknown"
    assert "Turn the PC on once" in res["message"]

@pytest.mark.asyncio
async def test_save_ip_only_without_mac(tmp_path, monkeypatch):
    import main
    monkeypatch.setenv("DECKY_PLUGIN_SETTINGS_DIR", str(tmp_path))
    main.SETTINGS_DIR = tmp_path
    async def none(ip): return None
    monkeypatch.setattr(main, "resolve_mac", none)
    res = await main.Plugin().save_config({"ip": "192.168.1.42"})
    assert res["ok"] is True
    assert res["config"]["mac"] == ""
    assert res["mac_resolved"] is False
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_resolve.py -q`
Expected: FAIL — functions not defined.

- [ ] **Step 3: Implement resolution**

Add a module constant `_ARP_PATH = Path("/proc/net/arp")` (module-level so tests can point it at a fixture). Implement exact-IP parsers (split lines, match field 0, take the HW address field: index 3 for `/proc/net/arp`, the token after `lladdr` for `ip neigh`, skipping `00:00:00:00:00:00`). Implement `resolve_mac`:

1. `ping -c 1 -W 1000 <ip>` in a subprocess, ignoring errors and capped at 2 s.
2. Read `_ARP_PATH` if it exists and try `_find_mac_in_arp`.
3. Run `ip neigh`, decode stdout, try `_find_mac_in_neigh`.
4. Return the first normalized MAC, else `None`.

In `wake`, before building the packet: when `cfg.mac` is empty, call `resolve_mac(cfg.ip)`; on success set `cfg.mac`, persist with `save_config(cfg)`; on failure return `{"error": "mac_unknown", "message": "MAC address unknown. Turn the PC on once, save again, or use Discover."}` and send nothing. Keep the existing send fan-out below unchanged.

Add to `Plugin`:

```python
async def learn_mac(self) -> dict:
    cfg = load_config()
    mac = await resolve_mac(cfg.ip)
    if mac:
        cfg.mac = mac
        save_config(cfg)
    return {"mac": mac}
```

Also update `Plugin.save_config` so that after `validate_config`, when `cfg.mac` is empty it calls `await resolve_mac(cfg.ip)` and stores the result, then persists. Return `{"ok": True, "config": asdict(cfg), "mac_resolved": bool(cfg.mac)}`; keep returning `{"error": str(e)}` on validation failure.

Note the module already has a `save_config(cfg)` function; the class method of the same name must keep calling the module function (it does today).

- [ ] **Step 4: Run backend tests**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_resolve.py
git commit -m "feat: learn MAC from ARP and cache it on wake"
```

---

### Task 3: Keypad modal and IP-first settings view

**WDD class:** dense

**Files:**
- Create: `src/KeypadModal.tsx`
- Rewrite: `src/SettingsView.tsx`
- Modify: `src/api.ts` (add `learnMac`)
- Modify: `src/index.tsx` (`HINT.needs_setup` line 19)

**Interfaces:**
- Produces: `KeypadModal({ title, initial, charset, maxLength, onCancel, onConfirm })` where `onConfirm(value: string)`; used for `ip` (`"0123456789."`, 15), `mac` (`"0123456789abcdef:"`, 17), `broadcast` (`"0123456789."`, 15), `probe_port` (`"0123456789"`, 5).
- Produces: `learnMac = callable<[], any>("learn_mac")` in `src/api.ts`.
- Consumes: `saveConfig(form)` returning `{config, mac_resolved}` from Task 2; `discover()` from the existing API.

- [ ] **Step 1: Write the keypad component**

`src/KeypadModal.tsx` renders a `PanelSection` titled `title`, a large read-only value line, and a keypad. Build rows by chunking `charset` into rows of at most 3, each row a `Focusable` with `flow-children="row"` containing `DialogButton`s (min width/height 48). Add a `⌫` button that removes the last character and is disabled when empty, plus `Cancel` and `OK` buttons (`OK` disabled when value is empty). Enforce `maxLength` and ignore characters not in `charset`. Import `DialogButton`, `Focusable`, `PanelSection`, `PanelSectionRow` from `@decky/ui`.

- [ ] **Step 2: Rewrite settings around IP**

`src/SettingsView.tsx` keeps `form` state and the `EMPTY` constant minus required MAC. Add `const [editing, setEditing] = React.useState<null | { key: keyof Config; title: string; charset: string; maxLength: number }>(null)` and `const [advanced, setAdvanced] = React.useState(false)` and `macMsg` state.

Render when `editing` is set: `<KeypadModal ... onCancel={() => setEditing(null)} onConfirm={(v) => { setForm(...); setEditing(null); }} />`. For `key === "ip"`, the confirm also calls `saveConfig({ ...form, ip: v })`.

Main layout:
- Alias row: a `TextField` inside `<div className="wake-pc-alias">` with a scoped `<style>` rule `.wake-pc-alias input { background: #16202d; color: #dcdedf; border: 1px solid #2a3f5a; border-radius: 4px; padding: 8px; }`.
- PC address row: `192.168.1.42` text (or `Not set`) plus two `ButtonItem`s: `Enter IP` (opens keypad) and `Find on network` (existing `scan`).
- After a save: if `r.config.mac` is set show `Found MAC aa:bb:cc:dd:ee:ff`; else show `Saved. Turn the PC on once and save again so I can learn its MAC.`
- `Advanced ▸` toggle showing MAC, Broadcast and Probe port rows, each with an `Enter`/`Change` button opening the keypad with the charsets above, and one `Save` button that calls `saveConfig(form)` and surfaces `r.error` inline.
- Remove the old `validate()` "Required" logic and the old field list. Keep `Send test packet` and `Test status probe`.

- [ ] **Step 3: Add the API callable and update the hint**

`src/api.ts`: `export const learnMac = callable<[], any>("learn_mac");` and export it. In Settings, call `learnMac()` from a `Retry learning MAC` button shown when `mac` is empty. In `src/index.tsx`, set `HINT.needs_setup` to `Open Settings and enter the PC's IP.`

- [ ] **Step 4: Build and typecheck**

Run: `pnpm build`
Expected: build succeeds and `dist/index.js` is written.

- [ ] **Step 5: Commit**

```bash
git add src/KeypadModal.tsx src/SettingsView.tsx src/api.ts src/index.tsx dist/index.js
git commit -m "feat: IP-first settings with gamepad keypad"
```

---

### Task 4: Documentation and installable package

**WDD class:** wiring

**Files:**
- Modify: `README.md`
- Modify: `dist/index.js` (rebuild output)

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Rewrite the setup sections**

In `README.md`: quick start becomes "turn the PC on once → Settings → Enter IP (keypad) or Find on network → save; the plugin learns the MAC → Wake". Replace the required MAC/IP wording and the field table: `PC IP` required, `MAC` learned automatically (editable under Advanced), `Broadcast` derived from the IP, `Probe port` optional. Add a troubleshooting row: `Wake says "MAC address unknown"` → `Turn the PC on and press Save or Retry learning MAC; wake needs the MAC learned while it is visible.`

- [ ] **Step 2: Run backend tests, build and package**

Run: `python -m pytest -q && pnpm build && pnpm package`
Expected: tests pass, `wake-pc.zip` is produced with the `wake-pc/` top-level folder.

- [ ] **Step 3: Verify the zip contents**

Run: `unzip -l wake-pc.zip`
Expected: `wake-pc/dist/index.js`, `wake-pc/main.py`, `wake-pc/plugin.json`, `wake-pc/package.json`, `wake-pc/README.md`.

- [ ] **Step 4: Commit**

```bash
git add README.md wake-pc.zip dist/index.js
git commit -m "docs: describe IP-only setup"
```

---

## Manual verification (after install on the Deck)

- Settings shows Alias, PC address, `Enter IP`, `Find on network`; no white input for the IP.
- Entering `192.168.1.42` with the keypad works without the Steam keyboard, saves, and either shows the learned MAC or the "turn the PC on once" message.
- With the PC on, saving learns the MAC and Wake still works after the PC is shut down.
- With the PC off and no MAC learned, Wake shows the `MAC address unknown` message and sends nothing.
