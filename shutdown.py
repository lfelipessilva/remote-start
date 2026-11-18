import os
import base64
import tempfile
import asyncio
from pathlib import Path
from config import load_config, save_config

def _settings_dir():
    try:
        import main
        if hasattr(main, "SETTINGS_DIR"):
            return main.SETTINGS_DIR
    except Exception:
        pass
    from config import SETTINGS_DIR
    return SETTINGS_DIR
def _ssh_key_path() -> Path:
    return _settings_dir() / "shutdown_key"


def _ssh_pub_path() -> Path:
    return _settings_dir() / "shutdown_key.pub"


def _known_hosts_path() -> Path:
    return _settings_dir() / "known_hosts"


def _askpass_path() -> Path:
    return _settings_dir() / "askpass.sh"


def ensure_askpass_helper() -> str:
    _settings_dir().mkdir(parents=True, exist_ok=True)
    path = _askpass_path()
    path.write_text('#!/bin/sh\nprintf \'%s\\n\' "$WAKE_PC_SSH_PASSWORD"\n')
    os.chmod(path, 0o700)
    return str(path)


async def ensure_shutdown_key():
    """Return (private key path, public key line), generating on first use."""
    _settings_dir().mkdir(parents=True, exist_ok=True)
    key = _ssh_key_path()
    pub = _ssh_pub_path()
    if not (key.exists() and pub.exists()):
        for path in (key, pub):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        proc = await asyncio.create_subprocess_exec(
            "ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "decky-wake-pc",
            "-f", str(key),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        _, err = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(err.decode(errors="ignore").strip() or "ssh-keygen failed")
        os.chmod(key, 0o600)
        os.chmod(pub, 0o644)
    return str(key), pub.read_text().strip()


def _encode_powershell(script: str) -> str:
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")


def _key_install_script(public_key: str) -> str:
    key = public_key.replace("'", "''")
    return f"""$key = '{key}'
$userKey = Join-Path $env:USERPROFILE '.ssh\\authorized_keys'
New-Item -ItemType Directory -Force -Path (Split-Path $userKey) | Out-Null
if (-not (Test-Path $userKey)) {{ New-Item -ItemType File -Path $userKey | Out-Null }}
if (-not (Select-String -Path $userKey -SimpleMatch $key -Quiet -ErrorAction SilentlyContinue)) {{
  Add-Content -Path $userKey -Value $key
}}
try {{
  $adminKey = Join-Path $env:ProgramData 'ssh\\administrators_authorized_keys'
  New-Item -ItemType Directory -Force -Path (Split-Path $adminKey) | Out-Null
  if (-not (Test-Path $adminKey)) {{ New-Item -ItemType File -Path $adminKey | Out-Null }}
  if (-not (Select-String -Path $adminKey -SimpleMatch $key -Quiet -ErrorAction SilentlyContinue)) {{
    Add-Content -Path $adminKey -Value $key
  }}
  icacls $adminKey /inheritance:r /grant '*S-1-5-32-544:F' /grant '*S-1-5-18:F' | Out-Null
}} catch {{ }}
Write-Output 'ok'
"""


def _key_install_remote_command(public_key: str) -> str:
    return "powershell -NoProfile -NonInteractive -EncodedCommand " + _encode_powershell(
        _key_install_script(public_key)
    )


OPENSSH_ENABLE_COMMAND = (
    "Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0; "
    "Start-Service sshd; "
    "Set-Service -Name sshd -StartupType Automatic; "
    "New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server (sshd)' "
    "-Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22"
)

SSH_MESSAGES = {
    "ssh_unavailable": "Cannot reach the PC over SSH. Enable OpenSSH Server on the PC and try again.",
    "auth_failed": "Wrong Windows username or password.",
    "host_key_changed": "The PC's SSH host key changed. Reset the shutdown setup in Settings, then configure again.",
    "timeout": "The PC did not answer in time. Check that it is on and reachable.",
    "key_install_failed": "Connected, but the SSH key could not be installed. Try the setup again.",
    "ssh_error": "The SSH command failed. Check that OpenSSH Server is enabled on the PC.",
    "missing_ip": "Enter the PC IP address in Settings first.",
}


def _ssh_error(stderr: str) -> str:
    s = (stderr or "").lower()
    if "connection refused" in s or "no route to host" in s or "could not resolve" in s:
        return "ssh_unavailable"
    if "permission denied" in s:
        return "auth_failed"
    if "host key verification failed" in s or "remote host identification has changed" in s:
        return "host_key_changed"
    if "timed out" in s or "timeout" in s:
        return "timeout"
    return "ssh_error"


def _ssh_failure(code: str, *, command: str = "", detail: str = "") -> dict:
    message = SSH_MESSAGES.get(code, SSH_MESSAGES["ssh_error"])
    if code == "key_install_failed" and detail:
        message = f"{message} ({detail})"
    out = {"error": code, "message": message}
    if command:
        out["command"] = command
    return out


def _ssh_base_args(user: str, ip: str) -> list:
    return [
        "ssh", "-F", "/dev/null",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", f"UserKnownHostsFile={_known_hosts_path()}",
        "-o", "ConnectTimeout=8",
        "-o", "LogLevel=ERROR",
        "-l", user, ip,
    ]


async def _run_ssh(args: list, env=None, timeout: float = 30.0):
    """Run ssh and always return (returncode|None, stdout, stderr)."""
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
        return proc.returncode, out.decode(errors="ignore"), err.decode(errors="ignore")
    except asyncio.TimeoutError:
        if proc is not None:
            try:
                proc.kill()
            except Exception:
                pass
            try:
                await proc.wait()
            except Exception:
                pass
        return None, "", "timed out"
    except Exception as e:
        return None, "", str(e)


def _user_candidates(user: str) -> list:
    out = [user]
    if "\\" in user:
        bare = user.rsplit("\\", 1)[1].strip()
        if bare and bare not in out:
            out.append(bare)
    return out


async def configure_shutdown(user: str, password: str) -> dict:
    user = (user or "").strip()[:64]
    if not user or not password:
        return {"error": "invalid_credentials", "message": "Enter the Windows username and password."}
    cfg = load_config()
    if not cfg.ip:
        return _ssh_failure("missing_ip")
    try:
        _esk = ensure_shutdown_key
        try:
            import main
            if hasattr(main, "ensure_shutdown_key"):
                _esk = main.ensure_shutdown_key
        except Exception:
            pass
        key_path, public_key = await _esk()
    except Exception as e:
        return {"error": "key_generation_failed", "message": str(e)}
    _eah = ensure_askpass_helper
    try:
        import main
        if hasattr(main, "ensure_askpass_helper"):
            _eah = main.ensure_askpass_helper
    except Exception:
        pass
    askpass = _eah()
    remote = _key_install_remote_command(public_key)
    fallback_command = remote

    env = os.environ.copy()
    env.update({
        "WAKE_PC_SSH_PASSWORD": password,
        "SSH_ASKPASS": askpass,
        "SSH_ASKPASS_REQUIRE": "force",
        "DISPLAY": env.get("DISPLAY", ":0"),
    })

    last_code = "ssh_error"
    last_detail = ""
    working_user = ""
    for candidate in _user_candidates(user):
        args = _ssh_base_args(candidate, cfg.ip) + [
            "-o", "PreferredAuthentications=password,keyboard-interactive",
            "-o", "PubkeyAuthentication=no",
            remote,
        ]
        code, _, err = await _run_ssh(args, env=env, timeout=30.0)
        if code == 0:
            working_user = candidate
            break
        last_code = "timeout" if code is None else _ssh_error(err)
        last_detail = (err or "").strip().splitlines()[-1] if (err or "").strip() else ""
        if last_code == "auth_failed":
            continue
        break

    if not working_user:
        command = OPENSSH_ENABLE_COMMAND if last_code == "ssh_unavailable" else ""
        return _ssh_failure(last_code, command=command, detail=last_detail)

    verify_args = _ssh_base_args(working_user, cfg.ip) + [
        "-i", key_path,
        "-o", "IdentitiesOnly=yes",
        "-o", "BatchMode=yes",
        "cmd", "/c", "echo", "ok",
    ]
    code, _, err = await _run_ssh(verify_args, timeout=15.0)
    if code != 0:
        mapped = "timeout" if code is None else _ssh_error(err)
        detail = (err or "").strip().splitlines()[-1] if (err or "").strip() else ""
        failure = mapped if mapped in ("host_key_changed", "timeout") else "key_install_failed"
        return _ssh_failure(failure, command=fallback_command, detail=detail)

    cfg.ssh_user = working_user
    save_config(cfg)
    return {"ok": True, "user": working_user}


async def shutdown_pc(cfg: Config) -> dict:
    if not cfg.ssh_user:
        return {
            "error": "shutdown_not_configured",
            "message": "Configure shutdown in Settings first.",
        }
    key_path = _ssh_key_path()
    if not key_path.exists():
        return {
            "error": "shutdown_not_configured",
            "message": "The shutdown key is missing. Configure shutdown again in Settings.",
        }
    args = _ssh_base_args(cfg.ssh_user, cfg.ip) + [
        "-i", str(key_path),
        "-o", "IdentitiesOnly=yes",
        "-o", "BatchMode=yes",
        "shutdown", "/s", "/t", "0",
    ]
    code, _, err = await _run_ssh(args, timeout=15.0)
    if code == 0:
        return {"ok": True}
    detail = (err or "").strip().lower()
    # Windows may drop the SSH connection as it shuts down, before ssh can
    # report the remote exit status. Treat that specific case as success.
    if code == 255 and (not detail or "connection closed" in detail or "broken pipe" in detail or "reset by peer" in detail):
        return {"ok": True, "connection_closed": True}
    mapped = "timeout" if code is None else _ssh_error(err)
    return _ssh_failure(mapped, detail=(err or "").strip().splitlines()[-1] if (err or "").strip() else "")


async def reset_shutdown_setup() -> dict:
    try:
        cfg = load_config()
        cfg.ssh_user = ""
        save_config(cfg)
        for path in (_ssh_key_path(), _ssh_pub_path(), _known_hosts_path(), _askpass_path()):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        return {"ok": True}
    except Exception as e:
        return {"error": str(e)}



__all__ = ['OPENSSH_ENABLE_COMMAND', 'SSH_MESSAGES', '_askpass_path', '_encode_powershell', '_key_install_remote_command', '_key_install_script', '_known_hosts_path', '_run_ssh', '_ssh_base_args', '_ssh_error', '_ssh_failure', '_ssh_key_path', '_ssh_pub_path', '_user_candidates', 'configure_shutdown', 'ensure_askpass_helper', 'ensure_shutdown_key', 'reset_shutdown_setup', 'shutdown_pc']
