# Wake PC Decky Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a Decky Loader plugin that wakes a home PC from the QAM, shows live on/off status, and fails loudly and helpfully on every problem.

**Architecture:** Python backend (`main.py`) owns config persistence, the magic packet, status probing, preflight, and a diagnostics log; the React frontend (`src/index.tsx` + views) owns the state machine, polling, and forms, calling backend methods through `@decky/api`. Backend is unit-tested with pytest; frontend is verified by build + manual install on the Deck.

**Tech Stack:** Decky Loader plugin API, Python 3.11 (system, on Deck), React 18 + TypeScript via the official Decky plugin template (pnpm + rollup), `@decky/api`, `@decky/ui`. Tests: pytest + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-11-18-wake-pc-decky-plugin-design.md`

## Global Constraints

- No root flag requested; plain UDP broadcast only.
- Magic packet: 6 × `0xFF` + MAC × 16; sent 3 rounds, ~150 ms apart, on UDP 9 and 7, to configured broadcast, derived `/24` subnet broadcast, and PC IP.
- Rate limit: one wake per 3 s.
- Wake timeout: 120 s, polling every 2 s during wake; 5 s while idle.
- Status: ping (`ping -c 1 -W 1`) OR TCP connect to `probe_port` (800 ms cap, 4 s overall cap).
- Config validated on load; corrupt file is backed up and reset to defaults with a toast.
- Alias trimmed, max 32 chars. MAC normalized to `aa:bb:cc:dd:ee:ff`. IPv4 validated.
- All user-facing strings and field labels as in the spec's UI sketch and error messages.

## Review Focus

1. A PC that is on but blocks ICMP and has no probe port set must not be reported Online — and the UI must explain why, not just say Offline.
2. A subnet broadcast derived by naive /24 truncation on a non-/24 network must not silently send to the wrong address — preflight should warn.
3. Wake must never be triggered twice by a double-tap; the 3 s gate must hold even if the first attempt errors out.
4. Corrupt config must not crash plugin load; it must be backed up and reset, with the toast fired once.
5. Polling must stop when the QAM panel unmounts; no lingering intervals or probes after close.

---

### Task 1: Scaffold the plugin

**WDD class:** scaffold

**Files:**
- Create: `plugin.json`
- Create: `package.json`
- Create: `tsconfig.json`
- Create: `rollup.config.js`
- Create: `main.py`
- Create: `src/index.tsx`
- Create: `README.md`

**Interfaces:**
- Produces: runnable `pnpm build` producing `dist/index.js`; `python -m pytest` runnable (empty).

- [ ] **Step 1:** Generate the scaffold from the official Decky plugin template (pnpm + rollup), setting name `wake-pc`, author placeholder, `api_version: 1`, and no root flag.
- [ ] **Step 2:** Verify `pnpm install && pnpm build` succeeds and `dist/index.js` exists.
- [ ] **Step 3:** Add `pyproject.toml` with pytest + pytest-asyncio; create `tests/` package.
- [ ] **Step 4:** Commit.

```bash
git add -A && git commit -m "chore: scaffold wake-pc decky plugin"
```

---

### Task 2: Backend config (validation, load, save, backup)

**WDD class:** dense

**Files:**
- Create: `main.py` (config section)
- Create: `tests/test_config.py`

**Interfaces:**
- Consumes: `decky.DECKY_PLUGIN_SETTINGS_DIR` env (fallback `~/.config/wake-pc`).
- Produces: `Config` dataclass `{ alias, mac, ip, broadcast, probe_port }`; `normalize_mac(str) -> str`; `validate_config(dict) -> Config | raises ValueError`; `load_config() -> Config`; `save_config(Config) -> None`; `reset_config(reason) -> Config`.

- [ ] **Step 1: Write failing tests** in `tests/test_config.py` covering: valid MAC in three formats normalized; invalid MAC raises; IPv4 validation; alias trim + 32-char cap; corrupt JSON backs up and resets; round-trip save/load; schema version stored.

```python
def test_normalize_mac_colon():
    assert normalize_mac("AA:BB:CC:DD:EE:FF") == "aa:bb:cc:dd:ee:ff"
def test_normalize_mac_raw():
    assert normalize_mac("aabbccddeeff") == "aa:bb:cc:dd:ee:ff"
def test_invalid_mac_raises():
    with pytest.raises(ValueError):
        normalize_mac("zz:bb:cc:dd:ee:ff")
def test_corrupt_config_resets(tmp_path, monkeypatch):
    ...
```

- [ ] **Step 2: Run** `pytest tests/test_config.py -v` — expect FAIL (not defined).
- [ ] **Step 3: Implement** config module in `main.py`: dataclass, validators, `load_config` (try/except, on `JSONDecodeError` rename to `.bak.<timestamp>` and write defaults, record reason in an in-memory `last_reset_reason`), `save_config` (atomic write via temp + rename), `schema_version = 1`.
- [ ] **Step 4: Run** tests — expect PASS.
- [ ] **Step 5: Commit.**

---

### Task 3: Backend wake (magic packet + fan-out)

**WDD class:** dense

**Files:**
- Modify: `main.py`
- Create: `tests/test_wake.py`

**Interfaces:**
- Consumes: `Config`.
- Produces: `build_magic_packet(mac: str) -> bytes` (102 bytes); `async wake(cfg: Config) -> dict` returning `{"mac", "sent_to": [str, ...]}`; `derive_subnet_broadcast(ip: str) -> str | None`.

- [ ] **Step 1: Write failing tests** with a fake socket: packet bytes exact; `wake` sends to each destination on ports 9 and 7, 3 rounds; a send failure to one destination is recorded but does not abort; `derive_subnet_broadcast("192.168.1.42") == "192.168.1.255"`; returns `None` on invalid IP.

- [ ] **Step 2: Run** `pytest tests/test_wake.py -v` — expect FAIL.
- [ ] **Step 3: Implement** in `main.py`: `build_magic_packet`, `derive_subnet_broadcast` (naive /24, returns None if IP invalid), `wake` using `asyncio` loop with `socket.socket(AF_INET, SOCK_DGRAM)` + `setsockopt(SO_BROADCAST, 1)`, catching per-send errors into `sent_to`/`failed`.
- [ ] **Step 4: Run** tests — expect PASS.
- [ ] **Step 5: Commit.**

---

### Task 4: Backend status probe

**WDD class:** dense

**Files:**
- Modify: `main.py`
- Create: `tests/test_status.py`

**Interfaces:**
- Produces: `async status(cfg: Config) -> dict` returning `{"online": bool, "method": "ping"|"tcp"|"none", "latency_ms": int | None}`; `preflight(cfg, deck_ip) -> list[str]` of problem strings.

- [ ] **Step 1: Write failing tests** mocking `asyncio.create_subprocess_exec` and `asyncio.open_connection`: ping success → online/ping; ping fail + TCP success → online/tcp; both fail → offline/none; overall cap 4 s; preflight flags missing MAC/IP, illegal broadcast, and /24 mismatch warning.

- [ ] **Step 2: Run** `pytest tests/test_status.py -v` — expect FAIL.
- [ ] **Step 3: Implement**: run ping and (if port set) TCP connect with `asyncio.gather` + `wait_for(..., 4.0)`; measure latency; preflight checks.
- [ ] **Step 4: Run** tests — expect PASS.
- [ ] **Step 5: Commit.**

---

### Task 5: Backend diagnostics + Decky Plugin class wiring

**WDD class:** wiring

**Files:**
- Modify: `main.py`

**Interfaces:**
- Produces: `class Plugin:` with `async def main`, `async def get_config`, `async def save_config`, `async def wake`, `async def status`, `async def preflight`, `async def test_wake`, `async def test_probe`, `async def get_diagnostics`; all returning JSON-serializable dicts. Diagnostics ring buffer of last 20 attempts.

- [ ] **Step 1:** Implement the `Plugin` class exposing the methods, mapping to Task 2–4 functions; wrap exceptions into `{"error": str}` returns (never raise across the RPC boundary).
- [ ] **Step 2:** Add diagnostics ring buffer capturing each wake/status with timestamp, outcome, destinations.
- [ ] **Step 3:** Add `test_wake` (one round, report destinations) and `test_probe` (single status call with method+latency).
- [ ] **Step 4:** Manual smoke: `python -c "import main"` imports cleanly.
- [ ] **Step 5: Commit.**

---

### Task 6: Frontend state machine + QAM panel

**WDD class:** dense

**Files:**
- Modify: `src/index.tsx`
- Create: `src/useWakeState.ts` (hook: state, polling, rate limit)

**Interfaces:**
- Consumes: backend `get_config`, `status`, `wake`, `preflight`.
- Produces: `State = "needs_setup" | "ready" | "checking" | "online" | "offline" | "waking" | "timed_out" | "error"`; hook `useWakeState()` returning `{ state, config, status, lastChecked, wake(), refresh(), canWake }`.

- [ ] **Step 1:** Implement state machine with transitions per spec; polling every 5 s while mounted, every 2 s while `waking`, stop on unmount.
- [ ] **Step 2:** Render status card with dot color + label + hint + "checked Xs ago"; Wake button disabled with reason; Refresh button.
- [ ] **Step 3:** Implement 3 s rate limit gate; show countdown on button.
- [ ] **Step 4:** Toast on wake success/timeout using `@decky/ui` toaster.
- [ ] **Step 5:** `pnpm build` succeeds; no TS errors.
- [ ] **Step 6: Commit.**

---

### Task 7: Settings view

**WDD class:** dense

**Files:**
- Create: `src/SettingsView.tsx`
- Modify: `src/index.tsx` (toggle)

**Interfaces:**
- Consumes: `get_config`, `save_config`, `test_wake`, `test_probe`.
- Produces: form with fields alias/mac/ip/broadcast/probe_port; per-field validation; Save/Cancel; test buttons with result lines.

- [ ] **Step 1:** Build form bound to config; validate on blur and on save; surface backend errors inline.
- [ ] **Step 2:** Wire Save → `save_config` → refresh state; Cancel discards.
- [ ] **Step 3:** Add "Send test packet" and "Test status probe" buttons showing destinations/method/latency.
- [ ] **Step 4:** `pnpm build` succeeds.
- [ ] **Step 5: Commit.**

---

### Task 8: Diagnostics view

**WDD class:** wiring

**Files:**
- Create: `src/Diagnostics.tsx`
- Modify: `src/index.tsx`

**Interfaces:**
- Consumes: `get_diagnostics`.

- [ ] **Step 1:** Collapsible "Last attempt" panel listing timestamp, outcome, destinations; "Copy diagnostics" copies a paste-ready block.
- [ ] **Step 2:** `pnpm build` succeeds.
- [ ] **Step 3: Commit.**

---

### Task 9: README + install instructions

**WDD class:** scaffold

**Files:**
- Modify: `README.md`

- [ ] **Step 1:** Document install (Decky CLI build → zip → "Install from zip"), configuration fields, WoL enablement, Windows Fast Startup note, AP client isolation, troubleshooting table mapping each failsafe message to a fix.
- [ ] **Step 2: Commit.**

---

### Task 10: End-to-end verification

**WDD class:** wiring

- [ ] **Step 1:** `pnpm build` clean; `pytest -q` all green.
- [ ] **Step 2:** Package zip with Decky CLI; install on Deck; configure; test wake from off and on; verify status transitions and toasts; verify corrupt-config recovery by editing the JSON.
- [ ] **Step 3:** Record results in `docs/superpowers/plans/...` verification note (append).
- [ ] **Step 4: Commit.**

---

## Self-review notes

Spec coverage: config (T2), wake (T3), status+preflight (T4), plugin wiring (T5), state machine+polling (T6), settings+tests (T7), diagnostics (T8), install docs (T9), e2e (T10). Review Focus items each map to T4 (1,2), T6 (3,5), T2 (4). No gaps found.