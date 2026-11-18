import React from "react";
import { callable } from "@decky/api";
import { PanelSection, PanelSectionRow, ButtonItem } from "@decky/ui";

const getConfig = callable<[], any>("get_config");
const saveConfig = callable<[any], any>("save_config");
const testWake = callable<[], any>("test_wake");
const testProbe = callable<[], any>("test_probe");

interface Config { alias: string; mac: string; ip: string; broadcast: string; probe_port: number; }

export function SettingsView({ onBack }: { onBack: () => void }) {
  const [form, setForm] = React.useState<Config>({ alias: "My PC", mac: "", ip: "", broadcast: "255.255.255.255", probe_port: 0 });
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [msg, setMsg] = React.useState("");
  const [testRes, setTestRes] = React.useState("");

  React.useEffect(() => {
    (async () => {
      const r: any = await getConfig();
      const cfg = r?.config ?? r;
      if (cfg) setForm({ alias: cfg.alias ?? "My PC", mac: cfg.mac ?? "", ip: cfg.ip ?? "", broadcast: cfg.broadcast ?? "255.255.255.255", probe_port: cfg.probe_port ?? 0 });
    })();
  }, []);

  const set = (k: keyof Config, v: any) => setForm((f) => ({ ...f, [k]: v }));

  const validate = () => {
    const e: Record<string, string> = {};
    if (!form.mac) e.mac = "required";
    if (!form.ip) e.ip = "required";
    if (!form.broadcast) e.broadcast = "required";
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const save = async () => {
    if (!validate()) return;
    const r: any = await saveConfig(form);
    if (r?.error) { setMsg(r.error); return; }
    const cfg = r?.config ?? r;
    if (cfg) setForm({ alias: cfg.alias ?? form.alias, mac: cfg.mac ?? form.mac, ip: cfg.ip ?? form.ip, broadcast: cfg.broadcast ?? form.broadcast, probe_port: cfg.probe_port ?? form.probe_port });
    setMsg("Saved");
  };

  const doTestWake = async () => {
    const r: any = await testWake();
    if (r?.error) { setTestRes(r.error); return; }
    setTestRes(`wake: dest=${JSON.stringify(r.destinations ?? r.sent_to)} failed=${JSON.stringify(r.failed)}`);
  };
  const doTestProbe = async () => {
    const r: any = await testProbe();
    if (r?.error) { setTestRes(r.error); return; }
    setTestRes(`probe: method=${r.method} latency=${r.latency_ms}ms online=${r.online}`);
  };

  const field = (k: keyof Config, label: string) => React.createElement(PanelSectionRow, null,
    React.createElement("div", null,
      React.createElement("label", null, label),
      React.createElement("input", { value: (form as any)[k], onChange: (e: any) => set(k, k === "probe_port" ? Number(e.target.value) : e.target.value), onBlur: validate }),
      errors[k] ? React.createElement("span", { style: { color: "red" } }, errors[k]) : null
    )
  );

  return React.createElement(PanelSection, { title: "Settings" },
    field("alias", "Alias"),
    field("mac", "MAC"),
    field("ip", "IP"),
    field("broadcast", "Broadcast"),
    field("probe_port", "Probe port"),
    React.createElement(PanelSectionRow, null, React.createElement(ButtonItem, { layout: "below", onClick: save }, "Save")),
    React.createElement(PanelSectionRow, null, React.createElement(ButtonItem, { layout: "below", onClick: () => onBack() }, "Cancel")),
    React.createElement(PanelSectionRow, null, React.createElement(ButtonItem, { layout: "below", onClick: doTestWake }, "Send test packet")),
    React.createElement(PanelSectionRow, null, React.createElement(ButtonItem, { layout: "below", onClick: doTestProbe }, "Test status probe")),
    msg ? React.createElement(PanelSectionRow, null, React.createElement("div", null, msg)) : null,
    testRes ? React.createElement(PanelSectionRow, null, React.createElement("div", null, testRes)) : null
  );
}