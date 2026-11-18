import React from "react";
import { definePlugin } from "@decky/api";
import { PanelSection, PanelSectionRow, ButtonItem, staticClasses } from "@decky/ui";
import { useWakeState, State } from "./useWakeState";
import { SettingsView } from "./SettingsView";
import { Diagnostics } from "./Diagnostics";

const DOT: Record<State, string> = {
  needs_setup: "#f59e0b", ready: "#94a3b8", checking: "#94a3b8", online: "#22c55e",
  offline: "#ef4444", waking: "#3b82f6", timed_out: "#f59e0b", error: "#ef4444",
};

const LABEL: Record<State, string> = {
  needs_setup: "Needs setup", ready: "Ready", checking: "Checking…", online: "Online",
  offline: "Offline", waking: "Waking…", timed_out: "Timed out", error: "Error",
};

const HINT: Partial<Record<State, string>> = {
  needs_setup: "Open Settings and enter the PC's IP.",
  offline: "No answer. If the PC is on, set a Probe port or allow ping through its firewall.",
  timed_out: "The packet was sent but the PC never answered. Check WoL and Fast Startup.",
  error: "Something failed. Open Diagnostics for details.",
};

function Panel() {
  const w = useWakeState();
  const [showSettings, setShowSettings] = React.useState(false);
  const [showDiagnostics, setShowDiagnostics] = React.useState(false);
  const [now, setNow] = React.useState(Date.now());
  React.useEffect(() => { const id = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(id); }, []);

  if (showSettings) return React.createElement(SettingsView, { onBack: () => { setShowSettings(false); w.refresh(); } });
  if (showDiagnostics) return React.createElement(Diagnostics, { onBack: () => { setShowDiagnostics(false); w.refresh(); } });

  const secs = Math.max(0, Math.ceil((w.rateUntil.current - now) / 1000));
  const blocked = !w.canWake || ["needs_setup", "error", "waking", "timed_out"].includes(w.state);
  const alias = w.config?.alias || "My PC";
  const method = w.status?.method && w.status.method !== "none" ? ` via ${w.status.method}` : "";
  const latency = w.status?.latency_ms != null ? ` (${w.status.latency_ms} ms)` : "";
  const checked = Math.max(0, Math.round((now - w.lastChecked) / 1000));

  const wakeLabel = w.state === "waking" ? "Waking…"
    : blocked ? `Wake (${LABEL[w.state].toLowerCase()})`
    : !w.canWake ? `Wake (${secs}s)` : `Wake ${alias}`;

  return React.createElement(PanelSection, { title: "Wake PC" },
    React.createElement(PanelSectionRow, null,
      React.createElement("div", { style: { display: "flex", alignItems: "center", gap: 8, padding: "2px 0" } },
        React.createElement("span", { style: { width: 10, height: 10, borderRadius: "50%", background: DOT[w.state] } }),
        React.createElement("span", { style: { fontWeight: 600 } }, alias),
        React.createElement("span", { style: { marginLeft: "auto", fontSize: 12, opacity: 0.8 } }, LABEL[w.state])
      )
    ),
    React.createElement(PanelSectionRow, null,
      React.createElement("div", { style: { fontSize: 11, opacity: 0.6, marginTop: -4 } },
        `${w.state}${method}${latency} · checked ${checked}s ago`
      )
    ),
    HINT[w.state] ? React.createElement(PanelSectionRow, null,
      React.createElement("div", { style: { fontSize: 11, opacity: 0.7, marginTop: -4 } }, HINT[w.state])
    ) : null,
    React.createElement(PanelSectionRow, null,
      React.createElement(ButtonItem, { layout: "below", onClick: () => { w.wake(); }, disabled: blocked }, wakeLabel)
    ),
    React.createElement(PanelSectionRow, null,
      React.createElement(ButtonItem, { layout: "below", onClick: () => w.refresh() }, "Refresh")
    ),
    React.createElement(PanelSectionRow, null,
      React.createElement(ButtonItem, { layout: "below", onClick: () => setShowSettings(true) }, "Settings")
    ),
    React.createElement(PanelSectionRow, null,
      React.createElement(ButtonItem, { layout: "below", onClick: () => setShowDiagnostics(true) }, "Diagnostics")
    )
  );
}

export default definePlugin(() => ({
  name: "Wake PC",
  title: React.createElement("div", { className: staticClasses.Title }, "Wake PC"),
  content: React.createElement(Panel),
  icon: React.createElement("div", null),
  onDismount() {},
}));