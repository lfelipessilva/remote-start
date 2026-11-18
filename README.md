# Wake PC

A Decky Loader plugin that turns your PC on from the Steam Deck's Quick Access
Menu using Wake-on-LAN, and shows whether the PC is currently on.

## Quick start (3 steps)

1. **Turn the PC on once** (the plugin learns its MAC from the network; a
   switched-off PC is invisible).
2. QAM → **Wake PC** → **Settings** → **Enter IP address** (the Steam keyboard
   opens) or **Find on network**, then tap your PC. Save.
3. **Press Wake.** Watch the dot: Offline → Waking → Online.

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
| Alias | Name shown in the panel (optional) | `Gaming PC` |
| PC IP | The PC's LAN IPv4 (required) | `192.168.1.42` |
| MAC address | Learned automatically; editable under Advanced | `aa:bb:cc:dd:ee:ff` |
| Broadcast | Derived from the IP; editable under Advanced | `192.168.1.255` |
| Probe port | Optional TCP port for status (445, 3389) | empty = ping + ARP |

Only **PC IP** is required. The first save (or **Find on network**) needs the PC
to be on so its MAC can be learned.

## What the buttons do

- **Wake** — sends the magic packet and watches for the PC to answer for up to
  2 minutes. Disabled while the PC is already online or during an attempt.
- **Refresh** — re-checks the status right now.
- **Settings** — enter the PC IP with the Steam on-screen keyboard, or tap
  **Find on network**. **Advanced** exposes MAC, broadcast and probe port if you
  ever need them.
- **Enter IP address** — opens a small dialog; type with the Steam keyboard and
  press **Save** (saves immediately).
- **Find on network** (in Settings) — scans the subnet and lists devices that
  are currently on; tap one to use its IP and MAC automatically.
- **Retry learning MAC** — shown while no MAC is known; run it with the PC on.
- **Send test packet** — sends one wake round and reports where it went. Useful
  to check the broadcast address without waiting for a boot.
- **Test status probe** — runs the online check once and shows the method
  (ping, ARP or TCP) and latency. Useful to confirm the IP is right.
- **Diagnostics** — last attempts, destinations, and a **Copy diagnostics**
  button for support.

## Status meanings

| Dot / state | Meaning |
|-------------|---------|
| `needs_setup` | PC IP missing — open Settings |
| `online` | PC answered ping, appeared in the LAN neighbour table (ARP), or accepted the probe port |
| `offline` | No answer. Either the PC is off, or the network is blocking ARP/ping |
| `waking` | Wake sent, waiting for the PC to answer |
| `timed_out` | 2 minutes passed with no answer |
| `error` | Backend call failed, or the MAC is still unknown — check Diagnostics |

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
| Wake says "MAC address unknown" | Turn the PC on (same network) and press **Save** or **Retry learning MAC**. The MAC must be learned while the PC is visible. |
| Status says Offline while PC is on | Make sure the Deck and PC are on the same subnet, then press Refresh. The plugin checks ping, the LAN neighbour table (ARP) and an optional Probe port. |
| Status is stale | Press Refresh; polling is every 5 s while the panel is open. |

Decky backend logs: `journalctl -u plugin_loader -n 100 --no-pager`.
