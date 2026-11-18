import React from "react";
import { ServerAPI } from "@decky/api";
import { PanelSection, PanelSectionRow, ButtonItem } from "@decky/ui";

interface Config { alias: string; mac: string; ip: string; broadcast: string; probe_port: number; }

export function SettingsView({ serverApi, onBack }: { serverApi: ServerAPI; onBack: () => void }) {
  const [form, setForm] = React.useState<Config>({ alias: "", mac: "", ip: "", broadcast: "", probe_port: 9 });
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [msg, setMsg] = React.useState("");
  const [testRes, setTestRes] = React.useState("");

  React.useEffect(() => {
    (async () => {
      const r: any = await serverApi.callPluginMethod("get_config", {});
      if (r?.config) setForm(r.config);
    })();
  }, [serverApi]);

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
    const r: any = await serverApi.callPluginMethod("save_config", form);
    if (r?.error) { setMsg(r.error); return; }
    if (r?.config) setForm(r.config);
    setMsg("Saved");
  };

  const testWake = async () => {
    const r: any = await serverApi.callPluginMethod("test_wake", {});
    if (r?.error) { setTestRes(r.error); return; }
    setTestRes(`wake: dest=${JSON.stringify(r.destinations)} failed=${JSON.stringify(r.failed)}`);
  };
  const testProbe = async () => {
    const r: any = await serverApi.callPluginMethod("test_probe", {});
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
    React.createElement(PanelSectionRow, null, React.createElement(ButtonItem, { layout: "below", onClick: testWake }, "Send test packet")),
    React.createElement(PanelSectionRow, null, React.createElement(ButtonItem, { layout: "below", onClick: testProbe }, "Test status probe")),
    msg ? React.createElement(PanelSectionRow, null, React.createElement("div", null, msg)) : null,
    testRes ? React.createElement(PanelSectionRow, null, React.createElement("div", null, testRes)) : null
  );
}