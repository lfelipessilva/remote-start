# Wake PC — IP-only setup and gamepad keypad

Date: 2026-11-18
Status: approved

## Intent

Make setup as small as the similar community plugins: type the PC's IP once, done.
This also fixes the current settings form: Steam's `TextField` renders as an
unstyled white box in the QAM, does not open the on-screen keyboard when tapped,
and Steam+X closes the Decky panel instead.

Why IP is enough: the magic packet contains the target MAC, but the MAC can be
looked up from the IP in the Deck's ARP/neighbour table and cached. The lookup
only works while (or shortly after) the PC is on, which is the same one-time
moment the current Discover flow already needs.

## Goals

- Required setup: alias (optional) + PC IP. Nothing else.
- Learn and cache the MAC from the IP automatically; derive the broadcast from
  the IP.
- Replace every required text entry with a gamepad-navigable keypad modal, so no
  Steam on-screen keyboard is needed.
- Keep working config from the current version (no reset on upgrade).

## Non-goals

- Waking a PC whose MAC was never learned while it was on.
- Multiple PCs, hostnames/mDNS, IPv6.
- Typing a free-form MAC/broadcast as the normal path (still possible under
  Advanced).

## Approaches

- **A — Keep `TextField`, style it dark and wrap it in `Focusable` (rejected).**
  Smallest change, but still depends on Steam's keyboard, which is the failing
  part.
- **B — Scan-only setup (rejected).** No typing at all, but cannot set up a PC
  that is currently off, and cannot enter a known IP.
- **C — IP-only config + custom keypad (chosen).** One required value, entered
  without the OSK; reuses the existing discovery as an alternative.

## Design

### Config (schema v2)

| field        | meaning                                      | source |
|--------------|----------------------------------------------|--------|
| `alias`      | display name                                 | user, optional |
| `ip`         | PC LAN IPv4 (required)                       | user |
| `mac`        | target MAC                                   | auto-resolved, editable under Advanced |
| `broadcast`  | wake destination; empty means derive from `ip` | auto-derived |
| `probe_port` | optional TCP status probe                    | Advanced |

On load, schema v1 files are migrated (keep alias/mac/ip/broadcast/probe_port,
bump to v2) instead of being reset. Corrupt files are still backed up and reset.

### MAC resolution

`resolve_mac(ip)`:

1. Ping the IP once (short timeout) to prime the ARP cache.
2. Read `/proc/net/arp` and `ip neigh`.
3. Return the MAC for that exact IP, else `None`.

`save_config` resolves when `mac` is empty and stores the result. `wake()`
resolves again if `mac` is still empty. If it cannot resolve, return
`{error: "mac_unknown"}` with a message telling the user to turn the PC on once
(or use Discover). This is the only new failure mode and it must be explained,
not silent.

### Backend interface

Unchanged callables plus:

- `save_config({ip, alias, ...})` — `mac` no longer required; resolves and returns
  the stored config including the learned `mac`.
- `resolve_mac` may also be exposed as a callable for the settings screen to
  refresh the cached MAC.

### Frontend

No `TextField` for required values. A reusable `KeypadModal` (dark Steam-styled,
`Focusable` buttons, Cancel/OK) accepts a character set and a max length:

- PC IP: digits + `.`
- MAC (Advanced): `0-9 a-f :` (normalized by the backend)
- Broadcast (Advanced): digits + `.`
- Probe port (Advanced): digits

Settings view:

```
Settings
 Alias        Gaming PC              [ Edit ]
 PC address   192.168.1.42     [ Enter IP ]
                         [ Find on network ]
 First time: turn the PC on and tap Find on
 network (or enter its IP). The MAC is learned
 automatically.
 ▸ Advanced   MAC · Broadcast · Probe port
```

- `Enter IP` opens the keypad; `OK` saves immediately (no separate Save button).
- `Find on network` runs the existing discovery; tapping a device sets IP + MAC.
- After an IP-only save, show the learned MAC or a one-line warning that the PC
  must be powered on once before Wake can work.
- Alias is optional and edited through a small modal with a TextField styled by a
  scoped CSS class; if the keyboard misbehaves it blocks nothing.
- Main panel hint for `needs_setup` becomes "Open Settings and enter the PC's IP".

## Testing

- pytest: IPv4 validation, IP-only `validate_config`, v1→v2 migration, corrupt
  config reset, ARP parsing for both sources, broadcast derivation, and
  wake-without-MAC returning `mac_unknown` when resolution fails.
- Frontend: `pnpm build` clean; manual check on the Deck that entering the IP with
  the keypad works without the Steam keyboard and that Wake boots the PC.

## Files

- `main.py` — schema v2, migration, `resolve_mac`, save/wake behaviour
- `src/KeypadModal.tsx` — new keypad modal
- `src/SettingsView.tsx` — IP-first layout, Advanced section
- `src/index.tsx` — hint text for the new setup flow
- `src/api.ts` — config shape, resolve callable
- `tests/` — config, migration, ARP, wake tests
- `README.md` — new setup instructions
