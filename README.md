# Wake PC

A Decky Loader plugin that turns your PC on from the Steam Deck's Quick Access
Menu using Wake-on-LAN, and shows whether the PC is currently on.

## Quick start (3 steps)

1. **Turn the PC on** (discovery can only see a machine that is on).
2. QAM → **Wake PC** → **Settings** → **Discover PC on network**, then tap your
   PC in the list. That fills in its IP and MAC. Save.
3. **Press Wake.** Watch the dot: Offline → Waking → Online.

Discovery sweeps your subnet and lists devices that answer, with their MACs.
A switched-off PC cannot be discovered, so this is a one-time setup step: after
you save the MAC, waking works while the PC is off.

If discovery doesn't find it, enter the MAC and IP by hand (see below).

## Where to find the values

### Windows

Open Command Prompt or PowerShell on the PC:

```bat
ipconfig /all
```

- **MAC address**: the *Physical Address* of the active adapter (e.g.
  `AA-BB-CC-DD-EE-FF`). Enter it as `AA:BB:CC:DD:EE:FF` or `AABBCCDDEEFF`.
- **PC IP**: the *IPv4 Address* of the same adapter (e.g. `192.168.1.42`).

To avoid the IP changing later, give the PC a DHCP reservation in your router,
or set a static IP.

### Linux

```sh
ip link          # MAC after "link/ether"
ip -4 addr       # IPv4 after "inet"
```

## What each field means

| Field | What to put | Example |
|-------|-------------|---------|
| Alias | Name shown in the panel | `Gaming PC` |
| MAC address | The PC's network card MAC | `aa:bb:cc:dd:ee:ff` |
| PC IP | The PC's LAN IPv4 (used for status) | `192.168.1.42` |
| Broadcast | Where the wake packet is sent | `255.255.255.255` |
| Probe port | Optional TCP port for status (22, 445, 3389) | empty = ping only |

Only **MAC** and **PC IP** are required. Defaults work for most home networks.

## What the buttons do

- **Wake** — sends the magic packet and watches for the PC to answer for up to
  2 minutes. Disabled while the PC is already online or during an attempt.
- **Refresh** — re-checks the status right now.
- **Settings** — edit the fields above. Nothing is written until you press Save.
  Text fields open the Steam on-screen keyboard, so they work from the gamepad.
- **Discover PC on network** (in Settings) — scans the subnet and lists devices
  that are currently on; tap one to fill in its IP and MAC automatically.
- **Send test packet** — sends one wake round and reports where it went. Useful
  to check the broadcast address without waiting for a boot.
- **Test status probe** — runs the online check once and shows the method
  (ping/TCP) and latency. Useful to confirm the IP is right.
- **Diagnostics** — last attempts, destinations, and a **Copy diagnostics**
  button for support.

## Status meanings

| Dot / state | Meaning |
|-------------|---------|
| `needs_setup` | MAC or IP missing — open Settings |
| `online` | PC answered ping or the probe port |
| `offline` | No answer. Either the PC is off, or it is on but blocks ICMP and no probe port is set |
| `waking` | Wake sent, waiting for the PC to answer |
| `timed_out` | 2 minutes passed with no answer |
| `error` | Backend call failed — check Diagnostics / Decky logs |

`offline` while the PC is actually on almost always means ICMP is blocked. Set
**Probe port** to a port the PC listens on (22 for SSH, 445 for SMB, 3389 for
RDP) and save.

## Enable Wake-on-LAN on the PC

- Enable **Wake on LAN / Wake on Magic Packet** in the BIOS/UEFI.
- Windows: Device Manager → network adapter → Properties → Power Management →
  allow this device to wake the computer; Advanced → *Wake on Magic Packet* =
  Enabled.
- The network card must stay powered while the PC is off (usually a BIOS
  "ErP" setting that must be disabled).

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

## Install / update

Build the zip:

```sh
pnpm install
pnpm package      # produces wake-pc.zip
```

The zip must contain one top-level folder named `wake-pc/`. `pnpm package`
handles that.

Install on the Deck:

```sh
scp wake-pc.zip deck@<deck-ip>:/home/deck/
ssh deck@<deck-ip>
unzip -o /home/deck/wake-pc.zip -d /tmp/wake-pc-install
sudo rm -rf /home/deck/homebrew/plugins/wake-pc
sudo cp -r /tmp/wake-pc-install/wake-pc /home/deck/homebrew/plugins/wake-pc
sudo systemctl restart plugin_loader
```

Or use Decky → Developer → *Install Plugin from ZIP File*.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Plugin does not appear in Decky | Zip had no `wake-pc/` top-level folder, or the file name did not match. Rebuild with `pnpm package` and reinstall. |
| `manifest is not defined` / `React is not defined` | Old build. Rebuild and reinstall; the current build uses `@decky/rollup`. |
| Wake sent but PC stays off | Check WoL in BIOS and NIC; disable Fast Startup; confirm same subnet. |
| Status says Offline while PC is on | Set a Probe port, or allow ICMP through the PC firewall. |
| Status is stale | Press Refresh; polling is every 5 s while the panel is open. |

Decky backend logs: `journalctl -u plugin_loader -n 100 --no-pager`.
