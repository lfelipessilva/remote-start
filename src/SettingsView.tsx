import React from "react";
import { PanelSection, PanelSectionRow, ButtonItem, TextField } from "@decky/ui";
import { Config, Device, getConfig, saveConfig, testWake, testProbe, discover } from "./api";

const EMPTY: Config = { alias: "My PC", mac: "", ip: "", broadcast: "255.255.255.255", probe_port: 0 };

export function SettingsView({ onBack }: { onBack: () => void }) {
  const [form, setForm] = React.useState<Config>(EMPTY);
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [msg, setMsg] = React.useState("");
  const [testRes, setTestRes] = React.useState("");
  const [scanning, setScanning] = React.useState(false);
  const [devices, setDevices] = React.useState<Device[]>([]);
  const [scanMsg, setScanMsg] = React.useState("");

  React.useEffect(() => {
    (async () => {
      const r: any = await getConfig();
      const cfg = r?.config ?? r;
      if (cfg) setForm({ ...EMPTY, ...cfg });
    })();
  }, []);

  const set = (k: keyof Config, v: any) => setForm((f) => ({ ...f, [k]: v }));

  const validate = () => {
    const e: Record<string, string> = {};
    if (!form.mac) e.mac = "Required";
    if (!form.ip) e.ip = "Required";
    if (!form.broadcast) e.broadcast = "Required";
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const save = async () => {
    if (!validate()) return;
    const r: any = await saveConfig(form);
    if (r?.error) { setMsg(r.error); return; }
    const cfg = r?.config ?? r;
    if (cfg) setForm({ ...EMPTY, ...cfg });
    setMsg("Saved");
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
      setScanMsg(list.length ? `Found ${list.length} device(s). Tap one to fill MAC and IP.` : "No devices answered. Is the PC on and on the same network?");
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
  };

  const doTestWake = async () => {
    const r: any = await testWake();
    if (r?.error) { setTestRes(r.error); return; }
    setTestRes(`Test packet sent to ${JSON.stringify(r.destinations ?? r.sent_to ?? [])}`);
  };

  const doTestProbe = async () => {
    const r: any = await testProbe();
    if (r?.error) { setTestRes(r.error); return; }
    setTestRes(`Probe: ${r.online ? "online" : "offline"} via ${r.method}${r.latency_ms != null ? ` (${r.latency_ms} ms)` : ""}`);
  };

  const text = (k: keyof Config, label: string, description?: string, numeric = false) =>
    React.createElement(PanelSectionRow, null,
      React.createElement(TextField, {
        label,
        description,
        value: String((form as any)[k] ?? ""),
        mustBeNumeric: numeric,
        onChange: (e: any) => set(k, numeric ? Number(e.target.value.replace(/[^0-9]/g, "")) : e.target.value),
        onBlur: validate,
      }),
      errors[k] ? React.createElement("div", { style: { color: "#ef4444", fontSize: 12, marginTop: 4 } }, errors[k]) : null
    );

  return React.createElement(PanelSection, { title: "Settings" },

    React.createElement(PanelSectionRow, null,
      React.createElement("div", { style: { fontSize: 12, opacity: 0.7, marginBottom: 4 } },
        "Not sure about MAC/IP? Turn the PC on, then run Discover and tap it in the list."
      )
    ),

    React.createElement(PanelSectionRow, null,
      React.createElement(ButtonItem, { layout: "below", onClick: scan, disabled: scanning }, scanning ? "Scanning network…" : "Discover PC on network")
    ),
    scanMsg ? React.createElement(PanelSectionRow, null,
      React.createElement("div", { style: { fontSize: 12, opacity: 0.8 } }, scanMsg)
    ) : null,

    ...devices.map((d) =>
      React.createElement(PanelSectionRow, { key: d.ip },
        React.createElement(ButtonItem, { layout: "below", onClick: () => pick(d) }, `${d.ip}   ·   ${d.mac}`)
      )
    ),

    text("alias", "Alias", "Name shown in the panel"),
    text("mac", "MAC address", "aa:bb:cc:dd:ee:ff"),
    text("ip", "PC IP", "The PC's LAN address, used to check if it is on"),
    text("broadcast", "Broadcast", "Usually 255.255.255.255"),
    text("probe_port", "Probe port (optional)", "22, 445, 3389… leave empty for ping only", true),

    React.createElement(PanelSectionRow, null,
      React.createElement(ButtonItem, { layout: "below", onClick: save }, "Save")
    ),
    React.createElement(PanelSectionRow, null,
      React.createElement(ButtonItem, { layout: "below", onClick: () => onBack() }, "Cancel")
    ),
    React.createElement(PanelSectionRow, null,
      React.createElement(ButtonItem, { layout: "below", onClick: doTestWake }, "Send test packet")
    ),
    React.createElement(PanelSectionRow, null,
      React.createElement(ButtonItem, { layout: "below", onClick: doTestProbe }, "Test status probe")
    ),
    msg ? React.createElement(PanelSectionRow, null, React.createElement("div", { style: { color: "#22c55e", fontSize: 12 } }, msg)) : null,
    testRes ? React.createElement(PanelSectionRow, null, React.createElement("div", { style: { fontSize: 12, opacity: 0.85 } }, testRes)) : null
  );
}