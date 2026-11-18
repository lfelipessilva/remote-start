# Remote Shutdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a confirmed "Shut down PC" action that bootstraps an SSH key with the Windows password once, then shuts the PC down over key-only SSH.

**Architecture:** The Deck generates an Ed25519 key pair in the plugin settings directory. A one-time Settings flow asks for the Windows username and password, uses password SSH to install the public key, verifies key-only SSH, and discards the password. The panel button then runs `shutdown /s /t 0` over key-only SSH.

**Tech Stack:** Python 3 / asyncio backend, Windows OpenSSH Server, React + `@decky/ui` frontend, pytest.

**Spec:** `docs/superpowers/specs/2026-11-18-remote-shutdown-design.md`

## Global Constraints

- Never persist, log, or pass the Windows password on a command line.
- The private key stays in the plugin settings directory with mode `0600`.
- Support local administrator and standard Windows accounts.
- Require confirmation before sending the shutdown command.
- Do not break existing config schema v1/v2 files.
- Keep the existing wake/status behavior unchanged.

## Review Focus

- Wrong Windows username or password: report `auth_failed`, do not save `ssh_user`.
- OpenSSH disabled: report `ssh_unavailable` and show the enable command.
- Host key changed: report `host_key_changed` instead of accepting it.
- Password appears in argv or config: tests must prove it does not.
- Non-admin account: key install must fall back to the user profile without failing.

---

### Task 1: Config schema v3

**Files:**
- Modify: `main.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Config.ssh_user: str`, `SCHEMA_VERSION = 3`, `SUPPORTED_SCHEMA_VERSIONS = (1, 2, 3)`.

- [ ] **Step 1: Write failing tests**

```python
def test_v3_config_preserves_ssh_user(tmp_path, monkeypatch):
    import main
    monkeypatch.setenv("DECKY_PLUGIN_SETTINGS_DIR", str(tmp_path))
    main.SETTINGS_DIR = tmp_path
    main.save_config(main.Config(ip="192.168.1.42", ssh_user="Luis"))
    cfg = main.load_config()
    assert cfg.ssh_user == "Luis"
    assert json.loads((tmp_path / "config.json").read_text())["schema_version"] == 3


def test_v2_config_migrates_to_v3(tmp_path, monkeypatch):
    import main
    monkeypatch.setenv("DECKY_PLUGIN_SETTINGS_DIR", str(tmp_path))
    main.SETTINGS_DIR = tmp_path
    (tmp_path / "config.json").write_text(json.dumps({
        "schema_version": 2, "alias": "My PC", "mac": "",
        "ip": "192.168.1.42", "broadcast": "192.168.1.255",
    }))
    cfg = main.load_config()
    assert cfg.ssh_user == ""
    assert json.loads((tmp_path / "config.json").read_text())["schema_version"] == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_config.py -q`
Expected: FAIL because `ssh_user` and schema 3 do not exist.

- [ ] **Step 3: Implement config changes**

Add `ssh_user: str = ""` to `Config`; read it in `validate_config` with `.strip()[:64]`; bump the schema constants.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_config.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_config.py
git commit -m "feat: add ssh_user to config schema v3"
```

---

### Task 2: Key, askpass, and key-install script helpers

**Files:**
- Modify: `main.py`
- Test: `tests/test_shutdown.py`

**Interfaces:**
- Produces: `async ensure_shutdown_key() -> tuple[str, str]`, `ensure_askpass_helper() -> str`, `_key_install_script(public_key: str) -> str`, `_encode_powershell(script: str) -> str`.

- [ ] **Step 1: Write failing tests**

```python
def test_key_install_script_contains_key_and_acl_sids():
    script = main._key_install_script("ssh-ed25519 AAAA test")
    assert "ssh-ed25519 AAAA test" in script
    assert "administrators_authorized_keys" in script
    assert "*S-1-5-32-544" in script
    assert "*S-1-5-18" in script


def test_encode_powershell_round_trips():
    script = "Write-Output 'ok'"
    encoded = main._encode_powershell(script)
    assert base64.b64decode(encoded).decode("utf-16le") == script


@pytest.mark.asyncio
async def test_ensure_shutdown_key_reuses_existing(tmp_path, monkeypatch):
    import main
    main.SETTINGS_DIR = tmp_path
    (tmp_path / "shutdown_key").write_text("private")
    (tmp_path / "shutdown_key.pub").write_text("ssh-ed25519 AAAA\n")
    key, pub = await main.ensure_shutdown_key()
    assert key == str(tmp_path / "shutdown_key")
    assert pub == "ssh-ed25519 AAAA"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_shutdown.py -q`
Expected: FAIL because helpers do not exist.

- [ ] **Step 3: Implement helpers**

Add the settings paths (`shutdown_key`, `shutdown_key.pub`, `known_hosts`, `askpass.sh`). Generate with `ssh-keygen -q -t ed25519 -N "" -C decky-wake-pc -f <key>`, chmod `0600`, and reuse when both files exist. The askpass script must print `"$WAKE_PC_SSH_PASSWORD"` and be mode `0700`. The PowerShell install script appends the public key to `%USERPROFILE%\.ssh\authorized_keys` and, best effort, to `%ProgramData%\ssh\administrators_authorized_keys`, then sets the admin-file ACL with SIDs `*S-1-5-32-544` and `*S-1-5-18`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_shutdown.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_shutdown.py
git commit -m "feat: add SSH key and key-install helpers"
```

---

### Task 3: Password bootstrap

**Files:**
- Modify: `main.py`
- Test: `tests/test_shutdown.py`

**Interfaces:**
- Produces: `_ssh_error(stderr: str) -> str`, `async configure_shutdown(user: str, password: str) -> dict`, `Plugin.configure_shutdown(self, user, password)`.
- Consumes: Task 2 helpers.

- [ ] **Step 1: Write failing tests**

```python
@pytest.mark.asyncio
async def test_configure_shutdown_installs_key_and_saves_user(tmp_path, monkeypatch):
    import main
    main.SETTINGS_DIR = tmp_path
    monkeypatch.setattr(main, "ensure_shutdown_key", async_key("key", "ssh-ed25519 AAAA"))
    monkeypatch.setattr(main, "ensure_askpass_helper", lambda: "/tmp/askpass.sh")
    main.save_config(main.Config(ip="192.168.1.42"))

    calls = []
    async def fake_exec(*args, **kwargs):
        calls.append((args, kwargs))
        proc = mock.MagicMock()
        proc.returncode = 0
        proc.communicate = mock.AsyncMock(return_value=(b"ok", b""))
        return proc

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    res = await main.configure_shutdown("Luis", "s3cret")
    assert res == {"ok": True, "user": "Luis"}
    assert main.load_config().ssh_user == "Luis"
    assert all("s3cret" not in " ".join(map(str, args)) for args, _ in calls)
    assert calls[0][1]["env"]["WAKE_PC_SSH_PASSWORD"] == "s3cret"


def test_ssh_error_mapping():
    assert main._ssh_error("ssh: connect to host 1.2.3.4 port 22: Connection refused") == "ssh_unavailable"
    assert main._ssh_error("Permission denied (publickey,password).") == "auth_failed"
    assert main._ssh_error("Host key verification failed.") == "host_key_changed"
    assert main._ssh_error("Connection timed out") == "timeout"
    assert main._ssh_error("something else") == "ssh_error"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_shutdown.py -q`
Expected: FAIL because `configure_shutdown` and `_ssh_error` do not exist.

- [ ] **Step 3: Implement the bootstrap**

Run password SSH with `-F /dev/null`, `StrictHostKeyChecking=accept-new`, the plugin `known_hosts`, `PreferredAuthentications=password,keyboard-interactive`, `PubkeyAuthentication=no`, `ConnectTimeout=8`, `LogLevel=ERROR`, and `-l <user>`. Put the password in the child environment as `WAKE_PC_SSH_PASSWORD`, set `SSH_ASKPASS` to the helper, `SSH_ASKPASS_REQUIRE=force`, and a `DISPLAY` value. Run the encoded PowerShell key-install script. Then verify key-only SSH (`BatchMode=yes`, `IdentitiesOnly=yes`, command `echo ok`). Save `ssh_user` only after verification succeeds. Return `{"ok": True, "user": user}` or `{"error": code, "message": human_message}`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_shutdown.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_shutdown.py
git commit -m "feat: bootstrap SSH key with Windows password"
```

---

### Task 4: Shutdown command

**Files:**
- Modify: `main.py`
- Test: `tests/test_shutdown.py`

**Interfaces:**
- Produces: `async shutdown_pc(cfg: Config) -> dict`, `Plugin.shutdown(self)`.

- [ ] **Step 1: Write failing tests**

```python
@pytest.mark.asyncio
async def test_shutdown_requires_ssh_user():
    res = await main.shutdown_pc(main.Config(ip="192.168.1.42"))
    assert res["error"] == "shutdown_not_configured"


@pytest.mark.asyncio
async def test_shutdown_runs_key_only_ssh(tmp_path, monkeypatch):
    import main
    main.SETTINGS_DIR = tmp_path
    (tmp_path / "shutdown_key").write_text("private")
    calls = []
    async def fake_exec(*args, **kwargs):
        calls.append(args)
        proc = mock.MagicMock()
        proc.returncode = 0
        proc.communicate = mock.AsyncMock(return_value=(b"", b""))
        return proc
    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    res = await main.shutdown_pc(main.Config(ip="192.168.1.42", ssh_user="Luis"))
    assert res == {"ok": True}
    assert "BatchMode=yes" in calls[0]
    assert "shutdown" in calls[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_shutdown.py -q`
Expected: FAIL because `shutdown_pc` does not exist.

- [ ] **Step 3: Implement shutdown**

Refuse without `ssh_user` or the private key. Run key-only SSH with `IdentitiesOnly=yes`, `BatchMode=yes`, `ConnectTimeout=8`, then `shutdown /s /t 0`. Return `{"ok": True}` on exit 0, otherwise `{"error": _ssh_error(stderr), "message": ...}`. Wire `Plugin.shutdown` to load the config and call it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest -q`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_shutdown.py
git commit -m "feat: shut down the PC over key-only SSH"
```

---

### Task 5: Setup UI

**Files:**
- Modify: `src/api.ts`, `src/SettingsView.tsx`
- Create: `src/ShutdownSetupModal.tsx`

**Interfaces:**
- Produces: `configureShutdown(user: string, password: string)`, `Config.ssh_user`, `openShutdownSetup(initialUser, onSubmit)`.
- Consumes: Task 3 backend method.

- [ ] **Step 1: Add API types and calls**

Add `ssh_user: string` to `Config`; export `configureShutdown` as `callable<[string, string], any>("configure_shutdown")`.

- [ ] **Step 2: Create the setup modal**

Build a `ConfirmModal` with a username `TextField` and a password `TextField` (`bIsPassword: true`), a hint that the password is used once and not stored, an OK button disabled until both fields are filled, and an `openShutdownSetup` wrapper that returns the values.

- [ ] **Step 3: Add the Settings section**

After the existing fields, add a "Shutdown" area with a **Configure shutdown** button (or **Reconfigure (user)**), the OpenSSH requirement hint, and a success/error message. On submit, set "Configuring shutdown…", call `configureShutdown`, then set `form.ssh_user` and show "Shutdown configured. The password was not saved."

- [ ] **Step 4: Build**

Run: `pnpm build`
Expected: build succeeds with no TypeScript errors.

- [ ] **Step 5: Commit**

```bash
git add src/api.ts src/SettingsView.tsx src/ShutdownSetupModal.tsx
git commit -m "feat: add shutdown setup UI"
```

---

### Task 6: Panel button, docs, and package

**Files:**
- Modify: `src/index.tsx`, `README.md`
- Test: `tests/test_shutdown.py` (error mapping coverage), `pnpm package`

**Interfaces:**
- Consumes: Task 4 `shutdown`, Task 5 `ssh_user`.

- [ ] **Step 1: Add the button**

Add **Shut down PC** below Wake. Disable it with "Shut down (configure in Settings)" until `config.ssh_user` exists. On press show a `ConfirmModal` ("Shut down the PC?"), call `shutdown`, toast success or the returned message, and show "Shutting down…" while in flight.

- [ ] **Step 2: Update README**

Add a "Shut down the PC" section: enable OpenSSH Server on Windows, enter the username/password once, key-only behavior, `whoami` tip, password not stored, admin account note, and troubleshooting (`ssh_unavailable`, `auth_failed`, `host_key_changed`).

- [ ] **Step 3: Run all checks**

Run: `python3 -m pytest -q && pnpm package`
Expected: all tests pass and `wake-pc.zip` is rebuilt.

- [ ] **Step 4: Commit**

```bash
git add src/index.tsx README.md wake-pc.zip
git commit -m "feat: add remote shutdown button and docs"
```
