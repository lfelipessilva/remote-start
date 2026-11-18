import React from "react";
import { PanelSection, PanelSectionRow, ButtonItem, TextField } from "@decky/ui";
import { Config, Device, getConfig, saveConfig, testWake, testProbe, discover, learnMac } from "./api";
import { KeypadModal } from "./KeypadModal";

const EMPTY: Config = { alias: "My PC", mac: "", ip: "", broadcast: "", probe_port: 0 };

const EDIT: Record<string, { title: string; charset: string; maxLength: number }> = {
  ip: { title: "PC IP", charset: "0123456789.", maxLength: 15 },
  mac: { title: "MAC address", charset: "0123456789abcdef:", maxLength: 17 },
  broadcast: { title: "Broadcast", charset: "0123456789.", maxLength: 15 },
  probe_port: { title: "Probe port", charset: "0123456789", maxLength: 5 },
};

const CSS = `.wake-pc-alias input { background: #16202d !important; color: #dcdedf !important; border: 1px solid #2a3f5a !important; border-radius: 4px !important; padding: 8px !important; }`;

const derive24 = (ip: string) => {
  const parts = (ip || "").split(".");
  return parts.length === 4 ? `${parts[0]}.${parts[1]}.${parts[2]}.255` : "";
};

const isValidIp = (v: string) =>
  /^\d{1,3}(\.\d{1,3}){3}$/.test(v) && v.split(".").every((p) => Number(p) <= 255);

const humanError = (e: string) =>
  e === "invalid ip" ? "Enter a valid IPv4 address, for example 192.168.1.42" : e;

export function SettingsView({ onBack }: { onBack: () => void }) {
  const [form, setForm] = React.useState<Config>(EMPTY);
  const [msg, setMsg] = React.useState("");
  const [macMsg, setMacMsg] = React.useState("");
  const [testRes, setTestRes] = React.useState("");
  const [scanning, setScanning] = React.useState(false);
  const [devices, setDevices] = React.useState<Device[]>([]);
  const [scanMsg, setScanMsg] = React.useState("");
  const [advanced, setAdvanced] = React.useState(false);
  const [editing, setEditing] = React.useState<keyof Config | null>(null);
  const [editError, setEditError] = React.useState("");
  const [ipError, setIpError] = React.useState("");
  const [broadcastTouched, setBroadcastTouched] = React.useState(false);

  React.useEffect(() => {
    (async () => {
      const r: any = await getConfig();
      const cfg = r?.config ?? r;
      if (cfg) {
        setForm({ ...EMPTY, ...cfg });
        setBroadcastTouched(!!cfg.broadcast && cfg.broadcast !== "255.255.255.255" && cfg.broadcast !== derive24(cfg.ip));
      }
    })();
  }, []);

  const set = (k: keyof Config, v: any) => setForm((f) => ({ ...f, [k]: v }));

  const payload = (next: Config): Config => ({ ...next, broadcast: broadcastTouched ? next.broadcast : "" });

  const persist = async (next: Config): Promise<boolean> => {
    setMsg("");
    setIpError("");
    try {
      const r: any = await saveConfig(payload(next));
      if (r?.error) {
        const m = humanError(r.error);
        setMsg(m);
        setIpError(m);
        return false;
      }
      const cfg = r?.config ?? next;
      setForm({ ...EMPTY, ...cfg });
      if (cfg.mac) {
        setMacMsg(`Found MAC ${cfg.mac}`);
        setMsg("Saved");
      } else {
        setMacMsg("Saved. Turn the PC on once and save again so I can learn its MAC.");
      }
      return true;
    } catch (e) {
      const m = String(e);
      setMsg(m);
      setIpError(m);
      return false;
    }
  };

  const confirmEdit = (value: string) => {
    if (!editing) return;
    const key = editing;
    if (key === "ip") {
      if (!isValidIp(value)) {
        setEditError("Enter a valid IPv4 address, for example 192.168.1.42");
        return;
      }
      setEditing(null);
      setEditError("");
      persist({ ...form, ip: value });
      return;
    }
    setEditing(null);
    setEditError("");
    if (key === "broadcast") setBroadcastTouched(true);
    const next: Config = { ...form, [key]: key === "probe_port" ? Number(value || 0) : value } as Config;
    setForm(next);
  };

  const scan = async () => {
    setScanning(true);
    setScanMsg("");
    setDevices([]);
    try {
      const r: any = await discover();
      if (r?.error) { setScanMsg(r.error); return; }
      const list: Device[] = r?.devices ?? [];
      setDevices(list);
      setScanMsg(list.length ? `Found ${list.length} device(s). Tap one to use its IP and MAC.` : "No devices answered. Is the PC on and on the same network?");
    } catch (e) {
      setScanMsg(String(e));
    } finally {
      setScanning(false);
    }
  };

  const pick = (d: Device) => {
    setForm((f) => ({ ...f, ip: d.ip, mac: d.mac }));
    setScanMsg(`Using ${d.ip}`);
    setDevices([]);
    setMacMsg(`Found MAC ${d.mac}`);
  };

  const retryMac = async () => {
    const r: any = await learnMac();
    if (r?.error) { setMacMsg(r.error); return; }
    if (r?.mac) {
      setForm((f) => ({ ...f, mac: r.mac }));
      setMacMsg(`Found MAC ${r.mac}`);
    } else {
      setMacMsg("Still no MAC. Turn the PC on (same network) and try again.");
    }
  };

  const doTestWake = async () => {
    const r: any = await testWake();
    if (r?.error) { setTestRes(r.message ?? r.error); return; }
    setTestRes(`Test packet sent to ${JSON.stringify(r.destinations ?? r.sent_to ?? [])}`);
  };

  const doTestProbe = async () => {
    const r: any = await testProbe();
    if (r?.error) { setTestRes(r.error); return; }
    setTestRes(`Probe: ${r.online ? "online" : "offline"} via ${r.method}${r.latency_ms != null ? ` (${r.latency_ms} ms)` : ""}`);
  };

  if (editing) {
    const spec = EDIT[editing];
    return React.createElement(KeypadModal, {
      title: spec.title,
      initial: String((form as any)[editing] ?? ""),
      charset: spec.charset,
      maxLength: spec.maxLength,
      error: editError,
      onCancel: () => { setEditing(null); setEditError(""); },
      onConfirm: confirmEdit,
    });
  }

  const valueRow = (label: string, value: string, key: keyof Config, action: string) =>
    React.createElement(PanelSectionRow, null,
      React.createElement("div", { style: { display: "flex", alignItems: "center", gap: 8 } },
        React.createElement("div", { style: { flex: 1, minWidth: 0 } },
          React.createElement("div", { style: { fontSize: 12, opacity: 0.65 } }, label),
          React.createElement("div", { style: { fontFamily: "monospace", wordBreak: "break-all" } }, value || "Not set")
        ),
        React.createElement(ButtonItem, { onClick: () => setEditing(key) }, action)
      )
    );

  return React.createElement(PanelSection, { title: "Settings" },
    React.createElement("style", null, CSS),

    React.createElement(PanelSectionRow, null,
      React.createElement("div", { className: "wake-pc-alias" },
        React.createElement(TextField, {
          label: "Alias",
          description: "Name shown in the panel (optional)",
          value: form.alias,
          onChange: (e: any) => set("alias", e.target.value),
        })
      )
    ),

    valueRow("PC address", form.ip, "ip", form.ip ? "Change" : "Enter IP"),
    ipError ? React.createElement(PanelSectionRow, null,
      React.createElement("div", { style: { color: "#ef4444", fontSize: 12 } }, ipError)
    ) : null,

    React.createElement(PanelSectionRow, null,
      React.createElement(ButtonItem, { layout: "below", onClick: scan, disabled: scanning }, scanning ? "Scanning network…" : "Find on network")
    ),
    scanMsg ? React.createElement(PanelSectionRow, null,
      React.createElement("div", { style: { fontSize: 12, opacity: 0.8 } }, scanMsg)
    ) : null,
    ...devices.map((d) =>
      React.createElement(PanelSectionRow, { key: d.ip },
        React.createElement(ButtonItem, { layout: "below", onClick: () => pick(d) }, `${d.ip}   ·   ${d.mac}`)
      )
    ),

    React.createElement(PanelSectionRow, null,
      React.createElement("div", { style: { fontSize: 12, opacity: 0.7 } },
        "First time: turn the PC on and tap Find on network, or enter its IP. The MAC is learned automatically."
      )
    ),
    macMsg ? React.createElement(PanelSectionRow, null,
      React.createElement("div", { style: { fontSize: 12, opacity: 0.85 } }, macMsg)
    ) : null,

    form.mac ? null : React.createElement(PanelSectionRow, null,
      React.createElement(ButtonItem, { layout: "below", onClick: retryMac }, "Retry learning MAC")
    ),

    React.createElement(PanelSectionRow, null,
      React.createElement(ButtonItem, { layout: "below", onClick: () => persist(form) }, "Save")
    ),

    React.createElement(PanelSectionRow, null,
      React.createElement(ButtonItem, { layout: "below", onClick: () => setAdvanced(!advanced) }, `${advanced ? "▾" : "▸"} Advanced`)
    ),
    advanced ? valueRow("MAC address", form.mac, "mac", form.mac ? "Change" : "Enter") : null,
    advanced ? valueRow("Broadcast", form.broadcast, "broadcast", form.broadcast ? "Change" : "Enter") : null,
    advanced ? valueRow("Probe port", String(form.probe_port || ""), "probe_port", form.probe_port ? "Change" : "Enter") : null,

    React.createElement(PanelSectionRow, null,
      React.createElement(ButtonItem, { layout: "below", onClick: doTestWake }, "Send test packet")
    ),
    React.createElement(PanelSectionRow, null,
      React.createElement(ButtonItem, { layout: "below", onClick: doTestProbe }, "Test status probe")
    ),
    msg ? React.createElement(PanelSectionRow, null, React.createElement("div", { style: { color: msg === "Saved" ? "#22c55e" : "#ef4444", fontSize: 12 } }, msg)) : null,
    testRes ? React.createElement(PanelSectionRow, null, React.createElement("div", { style: { fontSize: 12, opacity: 0.85 } }, testRes)) : null,
    React.createElement(PanelSectionRow, null,
      React.createElement(ButtonItem, { layout: "below", onClick: () => onBack() }, "Back")
    )
  );
}
