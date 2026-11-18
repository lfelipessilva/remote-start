# Wake PC

Decky Loader plugin to wake a PC via Wake-on-LAN from the Steam Deck's Quick Access Menu.

## Install

1. Build the plugin with the Decky CLI:
   ```sh
   decky plugin build
   ```
2. The build produces a zip in `dist/`.
3. On the Deck, open Decky Loader → Settings → **Install from zip** and select the zip.

No shell access required. The plugin does not request root.

## Configuration

Open the plugin panel in the QAM, then tap the gear icon for Settings. Fields:

| field | meaning | default |
|-------|---------|---------|
| Alias | display name, e.g. "Gaming PC" | `My PC` |
| MAC address | target MAC, `aa:bb:cc:dd:ee:ff` or 12 hex chars | required |
| PC IP | LAN IPv4, used for probing and as an extra packet target | required |
| Broadcast | subnet broadcast address | `255.255.255.255` |
| Probe port | optional TCP port proving the PC is up (22, 445, 3389) | ping only |

Validation happens on Save; invalid input shows a per-field error and Save stays disabled. If the PC's IP changes (DHCP), status shows Offline until the IP field is updated.

## Enable Wake-on-LAN on the PC

- Enable WoL in the BIOS/UEFI (often under "Power Management" / "Wake on LAN").
- In Windows, set the NIC's "Wake on Magic Packet" to Enabled in Device Manager.
- The NIC must stay powered in soft-off.

## Windows Fast Startup

Windows Fast Startup can leave the NIC in a state where the PC wakes from sleep but not from a full shutdown. If Wake works after sleep but not from shutdown, disable Fast Startup in Windows power options.

## AP client isolation

Some access points block client-to-client broadcast. If packets cannot be sent to `255.255.255.255`, try the subnet broadcast (e.g. `192.168.1.255`) in the Broadcast field.

## Troubleshooting

| Failsafe message | Fix |
|------------------|-----|
| `Offline after 2 min: the packet was sent but the PC never answered. Check that WoL is enabled and that Fast Startup is off.` | Enable WoL in BIOS/NIC; disable Windows Fast Startup. |
| `Probe failed for both ping and port 445. Try a different probe port or enable ICMP on the PC.` | Change Probe port or allow ICMP on the PC firewall. |
| `Broadcast 255.255.255.255 could not be sent: the Deck may be on client isolation. Try your subnet broadcast (e.g. 192.168.1.255).` | Use the subnet broadcast address in Broadcast. |
| `Deck is not on a network` | Connect the Deck to Wi-Fi/LAN. |
| `Add a MAC address in Settings` | Enter MAC and IP in Settings, then Save. |
| Corrupt config | Plugin backs up and resets to defaults with a toast on load. |
