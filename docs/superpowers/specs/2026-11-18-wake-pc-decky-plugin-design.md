# Wake PC — Decky Loader plugin design

Date: 2026-11-18
Status: proposed for approval

## Intent

Wake a home PC from the Steam Deck's Quick Access Menu with one press, and show
whether that PC is currently on, so streaming via Steam Link does not require
walking to the PC or opening another device. The user's primary need is turning
the PC on; status exists so they can trust that it worked.

## Goals

- Wake the configured PC from the QAM with one press.
- Show Online / Offline status for the PC inside the QAM, refreshed while the
  panel is open.
- Show a Waking state during an attempt and finish with a clear result toast.
- Let the user name the PC ("alias") and configure MAC, IP, and broadcast once
  through the plugin's own UI.
- Install as a normal Decky Loader plugin zip; no shell access required.

## Non-goals (v1)

- Shutdown / sleep / restart (needs a command channel into a running PC; a
  later pass, likely SSH).
- LAN discovery of the PC (a powered-off machine is invisible on the network, so
  discovery would only work while it is already on; later pass).
- Multiple PCs.
- Auto-wake when launching Steam Link.
- Scheduling, wake over the internet, IPv6, wake-on-ring.

## Constraints

- Decky Loader plugin: Python 3 backend (`main.py`, Decky `Plugin` class) plus a
  React/TypeScript frontend (`@decky/api`, `@decky/ui`) built to `dist/index.js`
  and packaged/installed through the Decky CLI or dev install.
- Deck and PC must be on the same subnet for the magic packet to arrive. Some
  access points block client-to-client broadcast; verify on the test network.
- Wake-on-LAN is already enabled on the PC. The PC's NIC must stay powered in
  soft-off; Windows Fast Startup is a known cause of "wakes from sleep but not
  from shutdown" and is a README troubleshooting note, not something the plugin
  can fix.
- The plugin backend runs with Decky's privileges. Sending a UDP broadcast needs
  nothing special, so the plugin does not request root.

## Approaches considered

- **A — Button only.** One Wake button, hand-entered MAC/broadcast. Smallest,
  but gives no feedback on whether the PC actually came up. Rejected as too thin
  for the user's stated wish to know on/off.
- **B — Console (chosen).** A plus live status, a Waking flow, and disabled Wake
  when already online. Delivers the primary need plus trust, with no extra
  dependencies on the PC.
- **C — Full manager.** B plus LAN discovery and SSH shutdown. Deferred: it adds
  credentials and PC-side setup, and would slow down proving the wake path.

## Design

### Configuration

A single JSON document in Decky's plugin settings directory, written by the
frontend through an RPC call and read by the backend.

| field         | meaning                                              | default            |
|---------------|------------------------------------------------------|--------------------|
| `alias`       | display name, e.g. "Gaming PC"                       | `My PC`            |
| `mac`         | target MAC, `aa:bb:cc:dd:ee:ff` or 12 hex chars      | empty (required)   |
| `ip`          | PC's LAN IPv4 address, used for probing and as an extra packet target | empty (required) |
| `broadcast`   | subnet broadcast address                             | `255.255.255.255`  |
| `probe_port`  | optional TCP port that proves the PC is up (e.g. 22, 445, 3389) | empty (ping only) |

Validation happens in the backend on save: MAC normalized to
`aa:bb:cc:dd:ee:ff`, IPv4 addresses checked, alias trimmed and length-capped.
Invalid input returns a readable error for the settings form. Config lives in
the backend because the backend needs it; nothing is written on every keystroke
— the form has an explicit Save.

The DHCP caveat is documented: if the PC's IP changes, status shows offline
until the IP field is updated.

### Backend interface (Decky callables)

- `get_config() -> dict`
- `save_config(dict) -> dict` — validates, normalizes, persists, returns stored form
- `wake() -> { "mac": str, "sent_to": [str, ...] }` — reports where packets went
- `status() -> { "online": bool, "method": "ping" | "tcp" | "none", "latency_ms": int | null }`

**wake()** builds the standard magic packet (6 × `0xFF` followed by the MAC
repeated 16 times) and sends it three rounds a fraction of a second apart, on
UDP ports 9 and 7, to: the configured broadcast address, a derived subnet
broadcast (Deck's own IPv4 with the last octet set to 255, assuming a /24 home
network), and the PC's IP directly. Returned `sent_to` is surfaced in an
optional diagnostics line, so a failure is debuggable without a shell.

**status()** runs ping (`ping -c 1 -W 1 <ip>`) and, when `probe_port` is set, a
TCP connect, in parallel with a short overall cap. Online if either succeeds.
Ping is the primary signal because it survives firewalls that block ports; the
TCP probe is an opt-in fallback for networks that drop ICMP. No ICMP raw sockets
are used.

Waking is deliberately not a backend loop: the frontend drives polling so that
UI state is the single source of truth and a closed QAM does not keep sending
probes.

### Frontend

The QAM tile is titled "Wake PC" (Decky registers titles at load time), and the
alias appears as the heading of the panel's status card:

```
┌────────────────────────────────────────┐
│  ● Online            Gaming PC         │
│  checked 3s ago                        │
│                                        │
│  [        Wake Gaming PC        ]      │
│  Refresh                     ⚙ Settings│
└────────────────────────────────────────┘

Settings view:
  Alias        [ Gaming PC            ]
  MAC address  [ aa:bb:cc:dd:ee:ff    ]
  PC IP        [ 192.168.1.42         ]
  Broadcast    [ 255.255.255.255      ]
  Probe port   [ 445        ] (optional)
  [ Save ]  [ Cancel ]      inline error line
```

- Status dot: green Online, grey Offline, amber Waking (with spinner).
- Wake is disabled and dimmed while the PC is online.
- Pressing Wake switches the card to Waking and polls `status()` every 2 s for up
  to 120 s. On success: toast "Gaming PC is online", dot green, polling stops. On
  timeout: toast that no response came back, with a one-line hint about power and
  WoL; the dot stays Offline. The plugin never reports success it did not
  observe.
- While the panel is open and idle, status polls every 5 s. Polling stops when
  the panel is hidden so a closed QAM is silent.
- Settings are a second view within the same panel, toggled by the gear; Save
  validates through the backend and shows the returned error inline.
- Components come from `@decky/ui` so D-pad focus and button hints work like the
  rest of the QAM.

### Failsafe and error UX (first-class requirement)

The plugin must never fail silently. Every state has a visible explanation and a next
step.

**States.** The card is always in exactly one of: `Needs setup` (no valid MAC/IP),
`Ready`, `Checking…`, `Online`, `Offline`, `Waking…`, `Timed out`, or `Error`.
Each state has its own dot color, label, and one-line hint. `Unknown` is never
shown as a bare value — if both probe methods fail for environmental reasons, the
card says so and points at the probe-port setting.

**Gating.** Wake is disabled until config is valid; the disabled button carries an
inline reason ("Add a MAC address in Settings"). Save is disabled while the form
has validation errors, and errors are shown per field, not as one blob.

**Preflight.** On panel open and before every wake, the backend checks that the
Deck has a usable network interface and that the configured broadcast is legal.
If not, the card shows the problem ("Deck is not on a network") instead of a
misleading Offline.

**Retries and fan-out.** Wake sends three rounds of packets to several
destinations (broadcast, derived subnet broadcast, PC IP) on ports 9 and 7. A
single failed send does not abort the attempt; the result lists what succeeded.

**Rate limiting.** Wake cannot be triggered more often than once every 3 s; the
button shows the countdown. Prevents packet spam and double-taps.

**Diagnostics.** Each attempt is recorded with timestamp, destinations, and
outcome, shown in a collapsible "Last attempt" panel and appended to the Decky
log. A "Copy diagnostics" button puts a paste-ready block on the clipboard for
support. The result toast names the PC and, on failure, the most likely cause.

**Test buttons.** Settings includes "Send test packet" (fires one round, reports
destinations) and "Test status probe" (runs `status()` once and shows method +
latency), so configuration can be verified without waiting for a real wake.

**Actionable failure messages.** Examples the UI must produce verbatim-ish:
- `Offline after 2 min: the packet was sent but the PC never answered. Check that
  WoL is enabled and that Fast Startup is off.`
- `Probe failed for both ping and port 445. Try a different probe port or enable
  ICMP on the PC.`
- `Broadcast 255.255.255.255 could not be sent: the Deck may be on client
  isolation. Try your subnet broadcast (e.g. 192.168.1.255).`

**Config safety.** Config is validated on load; a corrupt file is backed up and
reset to defaults with a toast, never crashing the plugin. Schema version is
stored for future migration.

**Controller UX.** All actions reachable by D-pad; focus order is status → Wake →
Refresh → Settings; toasts are non-blocking and dismissible; no modal blocks
input.

### Files

```
plugin.json            Decky metadata (name, author, api_version, publish)
main.py                Plugin class: config, wake, status, diagnostics
package.json           @decky/api + @decky/ui, build scripts
tsconfig.json
src/index.tsx          definePlugin, panel root, polling, state machine
src/SettingsView.tsx   settings form, test buttons, validation
src/Diagnostics.tsx    last attempt + copy
dist/index.js          build output
README.md              install, configuration, WoL/Fast Startup troubleshooting
```

## Testing and success criteria

- Plugin installs from a zip on the Deck, survives a Decky restart, and the
  config persists.
- With the PC off: pressing Wake boots it, the dot goes Offline → Waking →
  Online, and the toast fires.
- With the PC on: opening the panel shows Online within ~5 s and Wake is
  disabled.
- With a wrong MAC or IP: wake reports where it sent, status stays Offline, and
  the timeout toast appears. No false positives.
- Invalid MAC/IP in settings shows an inline error and does not save.

## Left to the builder

- Exact build tooling: take whatever the current official Decky plugin template
  (pnpm + rollup, or Decky CLI) provides rather than pinning versions here.
- Visual polish within the panel (spacing, icons) using `@decky/ui` primitives.
- Whether to compute the subnet broadcast from the Deck's actual netmask instead
  of assuming /24; /24 is acceptable for v1.

## Calls made in this design (worth a reviewer's eye)

- Ping-first status with an optional TCP port, rather than TCP-only.
- Explicit Save instead of live config writes.
- Frontend-driven polling rather than a backend wake-and-wait loop.
- Magic packets fanned out to several destinations to survive odd networks.
- No root flag requested.
