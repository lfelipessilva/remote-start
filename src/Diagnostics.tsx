import React from "react";
import { callable } from "@decky/api";
import { PanelSection, PanelSectionRow, ButtonItem } from "@decky/ui";

const getDiagnostics = callable<[], any>("get_diagnostics");

export function Diagnostics({ onBack }: { onBack: () => void }) {
  const [data, setData] = React.useState<any>(null);
  const [open, setOpen] = React.useState(false);
  const [copied, setCopied] = React.useState("");

  const load = React.useCallback(async () => {
    try { const r: any = await getDiagnostics(); setData(r); } catch (e) { setData({ error: String(e) }); }
  }, []);

  React.useEffect(() => { load(); }, [load]);

  const copy = async () => {
    const block = JSON.stringify(data, null, 2);
    try { await navigator.clipboard.writeText(block); setCopied("Copied"); } catch { setCopied("Copy failed"); }
    setTimeout(() => setCopied(""), 2000);
  };

  const entries = Array.isArray(data?.entries) ? data.entries : [];
  const last = entries.length ? entries[entries.length - 1] : (data?.last_attempt ?? data?.lastAttempt ?? null);
  return React.createElement(PanelSection, { title: "Diagnostics" },
    React.createElement(PanelSectionRow, null, React.createElement(ButtonItem, { layout: "below", onClick: load }, "Refresh")),
    React.createElement(PanelSectionRow, null, React.createElement(ButtonItem, { layout: "below", onClick: () => setOpen(!open) }, `Last attempt ${open ? "▲" : "▼"}`)),
    open ? React.createElement(PanelSectionRow, null, React.createElement("div", { style: { fontSize: 12 } },
      React.createElement("div", null, `timestamp: ${last?.timestamp ?? "-"}`),
      React.createElement("div", null, `outcome: ${last?.outcome ?? "-"}`),
      React.createElement("div", null, `destinations: ${JSON.stringify(last?.destinations ?? last?.dests ?? [])}`)
    )) : null,
    React.createElement(PanelSectionRow, null, React.createElement(ButtonItem, { layout: "below", onClick: copy }, "Copy diagnostics")),
    copied ? React.createElement(PanelSectionRow, null, React.createElement("div", null, copied)) : null,
    React.createElement(PanelSectionRow, null, React.createElement(ButtonItem, { layout: "below", onClick: onBack }, "Back"))
  );
}