import React from "react";
import { definePlugin } from "@decky/api";
import { PanelSection, PanelSectionRow, ButtonItem, staticClasses } from "@decky/ui";
import { useWakeState } from "./useWakeState";
import { SettingsView } from "./SettingsView";
import { Diagnostics } from "./Diagnostics";

const DOT: Record<string, string> = {
  needs_setup: "#f59e0b", ready: "#94a3b8", checking: "#94a3b8", online: "#22c55e",
  offline: "#ef4444", waking: "#3b82f6", timed_out: "#f59e0b", error: "#ef4444",
};

function Panel() {
  const w = useWakeState();
  const [showSettings, setShowSettings] = React.useState(false);
  const [showDiagnostics, setShowDiagnostics] = React.useState(false);
  const [now, setNow] = React.useState(Date.now());
  React.useEffect(() => { const id = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(id); }, []);
  const secs = Math.max(0, Math.ceil((w.rateUntil.current - now) / 1000));
  if (showSettings) return React.createElement(SettingsView, { onBack: () => { setShowSettings(false); w.refresh(); } });
  if (showDiagnostics) return React.createElement(Diagnostics, { onBack: () => { setShowDiagnostics(false); w.refresh(); } });
  return React.createElement(PanelSection, { title: "Wake PC" },
    React.createElement(PanelSectionRow, null,
      React.createElement("div", { style: { display: "flex", alignItems: "center", gap: 8 } },
        React.createElement("span", { style: { width: 10, height: 10, borderRadius: "50%", background: DOT[w.state] } }),
        React.createElement("span", null, w.state),
        React.createElement("span", { style: { marginLeft: "auto", fontSize: 12, opacity: 0.7 } }, `checked ${Math.round((now - w.lastChecked)/1000)}s ago`)
      )
    ),
    React.createElement(PanelSectionRow, null,
      React.createElement(ButtonItem, { layout: "below", onClick: async () => { await w.wake(); }, disabled: !w.canWake || ["needs_setup","error","waking","timed_out"].includes(w.state) }, (["needs_setup","error","waking","timed_out"].includes(w.state)) ? `Wake (${w.state})` : (w.canWake ? "Wake" : `Wake (${secs}s)`))
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