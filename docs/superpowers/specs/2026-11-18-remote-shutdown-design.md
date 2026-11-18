# Remote shutdown from the Deck

## Intent

Let the user turn the PC off from the same Quick Access Menu panel that turns
it on. Wake-on-LAN can only wake a machine, so shutdown needs a command
channel into Windows. The chosen setup asks for the Windows username and
password **once**, installs an SSH public key generated on the Deck, and then
uses key-only SSH for every shutdown. The password is never persisted.

## Goals

- A **Shut down PC** button in the panel, with a confirmation dialog.
- A one-time setup in Settings: Windows username + password.
- Generate an Ed25519 key pair on the Deck; the private key never leaves the
  Deck.
- Use the password only to install the public key on the PC, then discard it.
- Work with local administrator accounts and standard user accounts.
- Clear errors for: OpenSSH not enabled, bad credentials, host key mismatch,
  timeout, and key-install failure.
- No password in logs, config, argv, or diagnostics output.

## Non-goals

- Restart, sleep, hibernate, or lock.
- Enabling OpenSSH Server automatically (requires local admin on the PC).
- Supporting several PCs or several Windows accounts per PC.
- Password-based SSH for routine shutdowns.
- SMB/RPC, WinRM, or a custom agent on the PC.

## Constraints and assumptions

- The PC runs **OpenSSH Server** and allows password authentication for the
  one-time bootstrap. If it is not enabled, the plugin shows a ready-to-paste
  PowerShell command to enable it; after that the user retries.
- The Deck has `ssh` and `ssh-keygen` (SteamOS does).
- The plugin backend runs with access to its settings directory and can create
  files with restrictive permissions.
- The Windows account has a password. Windows Hello PIN alone is not enough.
- Shutdown is `shutdown /s /t 0` (no forced app termination). The confirmation
  dialog is the safety net against accidental presses.

## Approaches considered

1. **Password once, then key-only SSH (chosen).** Minimal repeated friction,
   no stored password, works with the Windows OpenSSH Server already present
   on modern Windows.
2. **One-paste PowerShell command with the public key.** No password handling,
   but requires the user to copy a long command to the PC. Good fallback and
   kept as the error hint, but not the primary flow.
3. **SMB/RPC or a custom agent.** Adds missing client packages or a new
   service to maintain, and usually still stores a password. Rejected.

## Design

### Config and files

- Bump `SCHEMA_VERSION` to `3`; keep `SUPPORTED_SCHEMA_VERSIONS = (1, 2, 3)`.
- Add `ssh_user: str = ""` to `Config`. It is set only after a successful
  bootstrap. No password field.
- `ssh_user` is backend-owned. The normal Settings save preserves it when the
  form omits it, and refuses to mark shutdown configured when the private key
  is missing.
- Key material lives in the plugin settings directory:
  - `shutdown_key` (mode `0600`)
  - `shutdown_key.pub`
  - `known_hosts`
  - `askpass.sh` (mode `0700`, generated on demand)
- Generate with:
  `ssh-keygen -t ed25519 -N "" -C "decky-wake-pc" -f <settings>/shutdown_key`
  and reuse the pair if it already exists.

### One-time bootstrap

Backend method: `configure_shutdown(user, password)`.

1. Validate that both values are non-empty; trim the username.
2. Ensure the key pair and askpass helper exist.
3. Connect with password auth:
   - `ssh -F /dev/null`
   - `-o StrictHostKeyChecking=accept-new`
   - `-o UserKnownHostsFile=<settings>/known_hosts`
   - `-o PreferredAuthentications=password,keyboard-interactive`
   - `-o PubkeyAuthentication=no`
   - `-o ConnectTimeout=8`
   - `-o LogLevel=ERROR`
   - `-l <user> <ip> <remote command>`
4. Provide the password through `SSH_ASKPASS` plus
   `SSH_ASKPASS_REQUIRE=force` and `DISPLAY` set. The helper script prints the
   value of an environment variable, so the password is never an argv value.
   If the Deck's OpenSSH is older than 8.4, fall back to `setsid -w` with the
   same askpass script.
5. Remote command: run an **encoded PowerShell script** (base64, UTF-16LE) to
   avoid shell quoting problems. The script appends the public key to:
   - `%USERPROFILE%\.ssh\authorized_keys`, and
   - `%ProgramData%\ssh\administrators_authorized_keys` (best effort).
   It creates directories and files when missing, avoids duplicate lines, and
   fixes the administrator file ACL with:
   `icacls <file> /inheritance:r /grant *S-1-5-32-544:F /grant *S-1-5-18:F`
   (SIDs, so localized Windows group names do not matter).
6. Verify key-only auth with a second SSH call (`BatchMode=yes`, `echo ok`).
7. Only then save `ssh_user`. Return `{ok: true, user}`.
8. Discard the password and delete any temporary helper state.

### Shutdown

Backend method: `shutdown()`:

- Refuse when `ssh_user` or the private key is missing.
- Run `ssh -F /dev/null -i <key> -o IdentitiesOnly=yes -o BatchMode=yes
  -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=<settings>/known_hosts
  -o ConnectTimeout=8 -l <user> <ip> shutdown /s /t 0`.
- All SSH calls use the same `known_hosts`, so the bootstrap pins the host key
  and later calls verify it. `accept-new` still accepts a new key when DHCP
  changes the IP, but rejects a changed key for a known host.
- Return `{ok: true}` on exit code 0. Windows may close the connection as it
  shuts down; exit code 255 with no stderr or a "connection closed"/"broken
  pipe"/"reset by peer" message is also success. Everything else maps to
  `auth_failed`, `ssh_unavailable`, `host_key_changed`, `timeout`, or
  `ssh_error`.

### Timeouts and recovery

- Bootstrap password call: 30 s; verification: 15 s; shutdown: 15 s. Timeouts
  kill the SSH process and return `timeout`.
- `Reset shutdown setup` deletes the key pair, `known_hosts`, the askpass
  helper, and clears `ssh_user`. It is the recovery path for a changed host key
  or a stuck configuration.
- `configure_shutdown` accepts `COMPUTER\user` and also retries the bare
  `user` after a failed password attempt, so the `whoami` output works for
  local accounts.
- Setup failure returns `{error, message, command?}`; `command` is the
  one-paste public-key install fallback shown in Settings as a copy action.

### Frontend

- `api.ts`: add `ssh_user` to `Config`; add `configureShutdown(user, password)`
  and `shutdownPc()`.
- Settings gets a **Shut down** section:
  - Shows "Configured for <user>" with a **Reconfigure** action, or
    **Configure shutdown** when unset.
  - A modal with **Windows username** and **Password** (`bIsPassword: true`),
    a hint that the password is used once and not stored, and the `whoami`
    tip for finding the username.
  - On success: "Shutdown configured. The password was not saved."
  - On failure: show the mapped error, plus the PowerShell command to enable
    OpenSSH when the connection was refused.
- Main panel: add **Shut down PC** below Wake. Disabled with
  "Configure shutdown in Settings" until `ssh_user` is set. When pressed, a
  `ConfirmModal` asks "Shut down the PC?"; on confirm call `shutdownPc()` and
  toast success or failure. It does not wait for the PC to go offline.

### Security notes

- Password travels only in the child process environment for the bootstrap
  command and is cleared afterwards.
- Private key and askpass helper are readable only by the plugin user
  (`0600` / `0700`).
- Host keys are pinned in the plugin settings directory; a mismatch is
  reported instead of silently accepted.
- The public key is inert without the private key, which stays on the Deck.

## Testing

- Unit: schema v3 round-trip, migration from v1/v2, `ssh_user` preserved.
- Unit: key generation is skipped when present; askpass/ssh argv never contains
  the password; encoded PowerShell command contains the public key and the
  ACL SIDs.
- Unit: shutdown success, non-zero exit, missing config, timeout, and stderr
  mapping.
- Manual on the Deck: configure against a Windows PC with OpenSSH Server,
  reboot the plugin loader, shut down, wake again.
- Manual error paths: OpenSSH disabled, wrong password, wrong username,
  PC offline.
