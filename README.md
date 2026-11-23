# Remote Start

A Decky Loader plugin that turns your PC on from the Steam Deck's Quick Access
Menu using Wake-on-LAN, shows whether the PC is currently on, and can shut it
down again over SSH.

| | |
|---|---|
| **Name** | Remote Start |
| **Plugin ID** | `Remote Start` |
| **Version** | 0.1.3 |
| **Author** | Luis Felipe |
| **Decky API** | 1 |
| **Requires** | Decky Loader, Steam Deck (SteamOS) |
| **Network** | Wake-on-LAN magic packet, ping/ARP for status, optional SSH for shutdown |

> **Download:** [Latest release](https://github.com/lfelipessilva/remote-start/releases/latest) ·
> [`remote-start.zip`](https://github.com/lfelipessilva/remote-start/releases/latest/download/remote-start.zip)
> — see [Install / update](#install--update).

## Install / update

[![Latest release](https://img.shields.io/github/v/release/lfelipessilva/remote-start)](https://github.com/lfelipessilva/remote-start/releases/latest)
[![Download remote-start.zip](https://img.shields.io/badge/download-remote--start.zip-38bdf8)](https://github.com/lfelipessilva/remote-start/releases/latest/download/remote-start.zip)

1. **Download the latest `remote-start.zip`** from the
   [Releases page](https://github.com/lfelipessilva/remote-start/releases/latest)
   (direct link:
   [`remote-start.zip`](https://github.com/lfelipessilva/remote-start/releases/latest/download/remote-start.zip)).
   Do this in Desktop Mode on the Deck, or transfer the file with `scp`.
2. In Decky Loader, open **Decky → Developer → Install Plugin from ZIP File**
   and select the downloaded `remote-start.zip`. If the Developer section is
   hidden, enable **Developer Mode** in Decky's settings first.
3. Restart Decky when prompted (or run `sudo systemctl restart plugin_loader`).
4. Open the Quick Access Menu → **Remote Start**.

To **update**, download the newest release and install it the same way. Your
settings and the shutdown SSH key are kept.

### Install from the command line (optional)

```sh
scp remote-start.zip deck@<deck-ip>:/home/deck/
ssh deck@<deck-ip>
unzip -o /home/deck/remote-start.zip -d /tmp/remote-start-install
sudo rm -rf "/home/deck/homebrew/plugins/Remote Start" "/home/deck/homebrew/plugins/remote-start.zip"
sudo cp -r "/tmp/remote-start-install/Remote Start" "/home/deck/homebrew/plugins/Remote Start"
sudo systemctl restart plugin_loader
```

> **Upgrading from the old "Wake PC" build:** the plugin was renamed, so the
> plugin folder and settings folder changed. Remove the old
> `homebrew/plugins/remote-start` folder (the command above does it), then open
> **Remote Start → Settings** and enter the PC IP once. The old config and
> shutdown key in `homebrew/settings/remote-start` are not reused and can be deleted.

### Build from source

```sh
pnpm install
pnpm package      # produces remote-start.zip
```

The zip contains one top-level folder named `Remote Start/`.

To publish a release (which uploads `remote-start.zip`), bump the version in
`plugin.json` and `package.json`, then push a matching tag:

```sh
git tag v0.1.3
git push origin v0.1.3
```

The workflow `.github/workflows/release.yml` builds the zip and attaches
`remote-start.zip` to the GitHub release.

## Quick start (3 steps)

1. **Turn the PC on once** (the plugin learns its MAC from the network; a
   switched-off PC is invisible).
2. QAM → **Remote Start** → **Settings** → **Enter IP address** (the Steam
   keyboard opens) or **Find on network**, then tap your PC. Save.
3. **Press Wake.** Watch the dot: Offline → Waking → Online.

Optional: enable OpenSSH Server on the PC and use **Settings → Configure
shutdown** to add a confirmed **Shut down PC** button. See
[Shut down the PC](#shut-down-the-pc-optional).

Only the PC's IP is required. The plugin looks the MAC up in the Deck's ARP table
and caches it, and derives the broadcast address from the IP. After that first
setup, waking works while the PC is off.

If you already know the IP, type it. If not, turn the PC on and use **Find on
network**.

## Where to find the values

Open Command Prompt or PowerShell on the PC:

```bat
ipconfig
```

- **PC IP**: the *IPv4 Address* of the active adapter (e.g. `192.168.1.42`).

You only need the IP. If you are curious, the MAC address is the *Physical
Address* of the same adapter; the plugin fills it in automatically.

To avoid the IP changing later, give the PC a DHCP reservation in your router,
or set a static IP.

## What each field means

| Field | What to put | Example |
|-------|-------------|---------|
| PC IP | The PC's LAN IPv4 (required) | `192.168.1.42` |
| MAC address | Learned automatically; editable under Advanced | `aa:bb:cc:dd:ee:ff` |
| Broadcast | Derived from the IP; editable under Advanced | `192.168.1.255` |

Only **PC IP** is required. The first save (or **Find on network**) needs the PC
to be on so its MAC can be learned.

## What the buttons do

- **Wake** — sends the magic packet and watches for the PC to answer for up to
  2 minutes. It stays available even when the PC is shown as online, because
  that check is best-effort (a stale ARP entry can briefly look online). It is
  only disabled for 3 seconds after a wake, to avoid accidental double sends.
- **Refresh** — re-checks the status right now.
- **Settings** — enter the PC IP with the Steam on-screen keyboard, or tap
  **Find on network**. **Advanced** exposes MAC and broadcast if you ever need
  them.
- **Enter IP address** — opens a small dialog; type with the Steam keyboard and
  press **Save** (saves immediately).
- **Find on network** (in Settings) — scans the subnet and lists devices that
  are currently on, with their PC names when the network shares them; tap one to
  use its IP and MAC automatically.
- **Retry learning MAC** — shown while no MAC is known; run it with the PC on.
- **Shut down PC** — enabled after the one-time shutdown setup in Settings.
  Asks for confirmation, then sends `shutdown /s /t 0` over key-only SSH.

## Status meanings

| Dot / state | Meaning |
|-------------|---------|
| `needs_setup` | PC IP missing — open Settings |
| `online` | PC answered ping or appeared in the LAN neighbour table (ARP); best-effort — Wake still works while this is shown |
| `offline` | No answer. Either the PC is off, or the network is blocking ARP/ping |
| `waking` | Wake sent, waiting for the PC to answer |
| `timed_out` | 2 minutes passed with no answer |
| `error` | Backend call failed, or the MAC is still unknown — open Settings and retry |

`offline` while the PC is actually on usually means the Deck cannot see the PC's
MAC at all: check that both are on the same subnet. Windows blocks ping by
default, which is why the plugin also uses the LAN neighbour table (ARP) to
detect an online PC.

## Enable Wake-on-LAN on the PC

- Enable **Wake on LAN / Wake on Magic Packet** in the BIOS/UEFI.
- Windows: Device Manager → network adapter → Properties → Power Management →
  allow this device to wake the computer; Advanced → *Wake on Magic Packet* =
  Enabled.
- The network card must stay powered while the PC is off (usually a BIOS
  "ErP" setting that must be disabled).

## Shut down the PC (optional)

Wake-on-LAN can only wake the PC, so shutdown uses the **OpenSSH Server**
built into Windows. Setup is one-time.

### 1. Enable OpenSSH Server on the PC

Open PowerShell **as administrator**. First check whether it is already
installed — on many Windows 11 builds it is, just stopped:

```powershell
Get-WindowsCapability -Online -Name OpenSSH.Server*
```

If it says `State : Installed`, skip to the service commands below.

Otherwise install it. `Add-WindowsCapability` is the built-in way, but it
downloads the feature from Windows Update and can take several minutes:

```powershell
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
```

**Faster alternative** (a ~10 MB installer instead of a Windows Update round
trip, usually under a minute):

```powershell
winget install --id Microsoft.OpenSSH.Beta -e --accept-source-agreements
```

Or download the MSI from
<https://github.com/PowerShell/Win32-OpenSSH/releases> and run
`msiexec /i OpenSSH-Win64-*.msi /qn`.

Then, in either case:

```powershell
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic
New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server (sshd)' `
  -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22
```

Check that it is listening with `Get-Service sshd`, then confirm from the Deck
with `ssh -p 22 <user>@<pc-ip>` (password prompt means it works).

### 2. Configure it in the plugin

1. PC on, same network as the Deck.
2. QAM → **Remote Start** → **Settings** → **Configure shutdown**.
3. **Windows username** — run `whoami` on the PC and copy the result, for
   example `desktop-pc\luis`. For a Microsoft account, use the local profile
   name shown by `whoami` and the Microsoft account password.
4. **Windows password** — used once to install an SSH key on the PC. It is
   **not saved**, not logged, and not passed on a command line.
5. Press **Configure**. The plugin installs the public key, verifies key-only
   login, and discards the password.

After that, **Shut down PC** appears in the panel. It asks for confirmation and
then runs `shutdown /s /t 0` over key-only SSH.

The plugin generates the key pair on the Deck; the private key stays in the
plugin settings directory and the public key is added to the PC's
`authorized_keys`. Administrator accounts use
`C:\ProgramData\ssh\administrators_authorized_keys`, which the setup handles
automatically.

If anything goes wrong, **Reset shutdown setup** in Settings removes the key,
the remembered username, and the pinned host key so you can configure again.

**Security note:** anyone who can read the Deck's plugin settings can use the
key to log in to that Windows account. Use a dedicated account if you prefer,
and remove the public key from the PC when you no longer need shutdown.

## Optional: log in to Windows automatically (Autologon)

Waking the PC only powers it on; Windows may still wait at the sign-in screen.
If you use the PC for streaming (Moonlight, Steam Remote Play), you can make
Windows sign in by itself with Microsoft's **Autologon** tool.

1. Download Autologon from
   [Microsoft Sysinternals](https://learn.microsoft.com/en-us/sysinternals/downloads/autologon),
   or install it from a terminal on the PC:

   ```bat
   winget install --id Sysinternals.Autologon -e
   ```

2. Unzip the download and run `Autologon64.exe` as administrator (use
   `Autologon.exe` on 32-bit Windows or `Autologon64a.exe` on ARM).
3. Accept the license prompt.
4. Fill in the account:
   - **Username** — the Windows user name; for a Microsoft account, the full
     email address.
   - **Domain** — the PC name for a local account; leave the domain if the PC is
     joined to one.
   - **Password** — the Windows password, not the PIN.
5. Click **Enable**, then reboot to confirm it signs in automatically.

To undo it, run Autologon again and click **Disable**. Holding **Shift** while
Windows starts skips autologon for that one boot.

**Security note:** Autologon stores the password encrypted in Windows' LSA
secrets, but the PC will sign in without asking. Only use it on a trusted home
PC, and skip it if the PC holds sensitive data.

## Common reasons a wake fails

- **Windows Fast Startup** — the PC wakes from sleep but not from shutdown.
  Disable Fast Startup in Control Panel → Power Options → *Choose what the power
  buttons do*.
- **Wrong network** — Deck and PC must be on the same subnet.
- **AP client isolation** — some routers block client-to-client broadcast. Put
  your subnet broadcast (e.g. `192.168.1.255`) in the Broadcast field.
- **PC IP changed** — DHCP handed out a new address; update the PC IP field.
- **Ethernet unplugged / Wi-Fi off** — WoL over Wi-Fi is often unreliable; a
  wired connection is the safe option.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Plugin does not appear in Decky | Download the latest `remote-start.zip` from the [Releases page](https://github.com/lfelipessilva/remote-start/releases/latest) and install it again. If building yourself, the zip must contain a `Remote Start/` top-level folder. |
| `manifest is not defined` / `React is not defined` | Old build. Rebuild and reinstall; the current build uses `@decky/rollup`. |
| Wake sent but PC stays off | Check WoL in BIOS and NIC; disable Fast Startup; confirm same subnet. |
| Wake says "MAC address unknown" | Turn the PC on (same network) and press **Save** or **Retry learning MAC**. The MAC must be learned while the PC is visible. |
| Status says Offline while PC is on | Make sure the Deck and PC are on the same subnet, then press Refresh. The plugin checks ping and the LAN neighbour table (ARP). |
| Status is stale | Press **Refresh**. The status is checked once when the panel opens, then only while a wake is in progress. |
| Shutdown says it cannot reach the PC | Enable **OpenSSH Server** on the PC and allow TCP port 22 in Windows Firewall. |
| Shutdown says wrong user or password | Enter the exact `whoami` output; for a Microsoft account, use the profile name and the account password, not the PIN. |
| Shutdown says the host key changed | The PC was reinstalled or replaced. Use **Reset shutdown setup**, then configure again. |
| Shutdown fails right after configuring | Check that key-only login works: the setup verifies it before saving. If it failed, reset and retry. |

Decky backend logs: `journalctl -u plugin_loader -n 100 --no-pager`.
