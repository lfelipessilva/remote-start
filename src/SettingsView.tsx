import React from "react";
import { PanelSection, PanelSectionRow, ButtonItem } from "@decky/ui";
import { Config, Device, getConfig, saveConfig, discover, learnMac, configureShutdown, resetShutdownSetup } from "./api";
import { openFieldEditor, validateField } from "./FieldModal";
import { openShutdownSetup } from "./ShutdownSetupModal";

const EMPTY: Config = { alias: "My PC", mac: "", ip: "", broadcast: "", ssh_user: "" };

const derive24 = (ip: string) => {
  const parts = (ip || "").split(".");
  return parts.length === 4 ? `${parts[0]}.${parts[1]}.${parts[2]}.255` : "";
};

const humanError = (e: string) =>
  e === "invalid ip" ? "Enter a valid IPv4 address, for example 192.168.1.42"
  : e === "invalid mac" ? "Enter 12 hex digits, for example AA:BB:CC:DD:EE:FF"
  : e;

export function SettingsView({ onBack }: { onBack: () => void }) {
  const [form, setForm] = React.useState<Config>(EMPTY);
  const [msg, setMsg] = React.useState("");
  const [macMsg, setMacMsg] = React.useState("");
  const [shutdownMsg, setShutdownMsg] = React.useState("");
  const [shutdownCommand, setShutdownCommand] = React.useState("");
  const [shutdownBusy, setShutdownBusy] = React.useState(false);
  const [scanning, setScanning] = React.useState(false);
  const [devices, setDevices] = React.useState<Device[]>([]);
  const [scanMsg, setScanMsg] = React.useState("");
  const [advanced, setAdvanced] = React.useState(false);
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

  const edit = (key: keyof Config) => {
    const value = String((form as any)[key] ?? "");
    const title = key === "ip" ? "PC IP address" : key === "mac" ? "MAC address" : "Broadcast address";
    const label = key === "ip" ? "IPv4 address" : key === "mac" ? "MAC" : "Broadcast";
    const kind = key as "ip" | "mac" | "broadcast";
    const hint =
      key === "ip" ? "The PC's LAN address, for example 192.168.1.42"
      : key === "mac" ? "Learned automatically. Leave empty to learn it again."
      : "Leave empty to derive it from the PC address.";

    openFieldEditor({
      title,
      label,
      hint,
      kind,
      initial: value,
      onConfirm: (v) => {
        if (validateField(v, kind)) return;
        if (key === "broadcast") setBroadcastTouched(true);
        const next: Config = { ...form, [key]: v } as Config;
        setForm(next);
        if (key === "ip") persist(next);
      },
    });
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
    setScanMsg(d.name ? `Using ${d.name} (${d.ip})` : `Using ${d.ip}`);
    setDevices([]);
    setMacMsg(`Found MAC ${d.mac}`);
  };

  const retryMac = async () => {
    try {
      const r: any = await learnMac();
      if (r?.error) { setMacMsg(r.error); return; }
      if (r?.mac) {
        setForm((f) => ({ ...f, mac: r.mac }));
        setMacMsg(`Found MAC ${r.mac}`);
      } else {
        setMacMsg("Still no MAC. Turn the PC on (same network) and try again.");
      }
    } catch (e) {
      setMacMsg(String(e));
    }
  };

  const setupShutdown = () => {
    openShutdownSetup(form.ssh_user, async (user, password) => {
      setShutdownBusy(true);
      setShutdownMsg("Connecting to the PC…");
      setShutdownCommand("");
      try {
        const r: any = await configureShutdown(user, password);
        if (r?.error) {
          setShutdownMsg(r.message ?? r.error);
          if (r.command) setShutdownCommand(r.command);
          return;
        }
        setForm((f) => ({ ...f, ssh_user: r.user ?? user }));
        setShutdownMsg("Shutdown configured. The password was not saved.");
      } catch (e) {
        setShutdownMsg(String(e));
      } finally {
        setShutdownBusy(false);
      }
    });
  };

  const resetShutdown = async () => {
    setShutdownBusy(true);
    setShutdownMsg("Resetting shutdown setup…");
    setShutdownCommand("");
    try {
      const r: any = await resetShutdownSetup();
      if (r?.error) { setShutdownMsg(r.error); return; }
      setForm((f) => ({ ...f, ssh_user: "" }));
      setShutdownMsg("Shutdown setup reset.");
    } catch (e) {
      setShutdownMsg(String(e));
    } finally {
      setShutdownBusy(false);
    }
  };

  const copyShutdownCommand = async () => {
    try {
      await navigator.clipboard.writeText(shutdownCommand);
      setShutdownMsg("Setup command copied.");
    } catch {
      setShutdownMsg("Could not copy the command.");
    }
  };

  const field = (label: string, value: string, key: keyof Config, action: string) =>
    React.createElement(PanelSectionRow, null,
      React.createElement(ButtonItem, {
        layout: "below",
        label,
        description: value || "Not set",
        onClick: () => edit(key),
      }, action)
    );

  return React.createElement(PanelSection, { title: "Settings" },
    field("PC address", form.ip, "ip", form.ip ? "Change IP address" : "Enter IP address"),
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
        React.createElement(ButtonItem, { layout: "below", onClick: () => pick(d) },
          `${d.name ? `${d.name}   ·   ` : ""}${d.ip}   ·   ${d.mac}`)
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
      React.createElement("div", { style: { fontWeight: 600, marginTop: 8 } }, "Shutdown")
    ),
    React.createElement(PanelSectionRow, null,
      React.createElement(ButtonItem, {
        layout: "below",
        onClick: setupShutdown,
        disabled: shutdownBusy || !form.ip,
      }, form.ssh_user ? `Reconfigure shutdown (${form.ssh_user})` : "Configure shutdown")
    ),
    React.createElement(PanelSectionRow, null,
      React.createElement("div", { style: { fontSize: 11, opacity: 0.7 } },
        "Requires OpenSSH Server on the PC. Your Windows password is used once and not saved."
      )
    ),
    shutdownMsg ? React.createElement(PanelSectionRow, null,
      React.createElement("div", {
        style: {
          fontSize: 12,
          color: /configured|reset|copied/i.test(shutdownMsg) ? "#22c55e" : "#ef4444",
        },
      }, shutdownMsg)
    ) : null,
    shutdownCommand ? React.createElement(PanelSectionRow, null,
      React.createElement(ButtonItem, { layout: "below", onClick: copyShutdownCommand }, "Copy setup command")
    ) : null,
    form.ssh_user ? React.createElement(PanelSectionRow, null,
      React.createElement(ButtonItem, { layout: "below", onClick: resetShutdown, disabled: shutdownBusy }, "Reset shutdown setup")
    ) : null,

    React.createElement(PanelSectionRow, null,
      React.createElement(ButtonItem, { layout: "below", onClick: () => setAdvanced(!advanced) }, `${advanced ? "▾" : "▸"} Advanced`)
    ),
    advanced ? field("MAC address", form.mac, "mac", form.mac ? "Change MAC" : "Enter MAC") : null,
    advanced ? field("Broadcast", form.broadcast, "broadcast", form.broadcast ? "Change broadcast" : "Enter broadcast") : null,

    msg ? React.createElement(PanelSectionRow, null, React.createElement("div", { style: { color: msg === "Saved" ? "#22c55e" : "#ef4444", fontSize: 12 } }, msg)) : null,
    React.createElement(PanelSectionRow, null,
      React.createElement(ButtonItem, { layout: "below", onClick: () => onBack() }, "Back")
    )
  );
}
