import { callable } from "@decky/api";

export interface Config {
  alias: string;
  mac: string;
  ip: string;
  broadcast: string;
  probe_port: number;
}

export interface Status {
  online: boolean;
  method: "ping" | "tcp" | "none";
  latency_ms: number | null;
}

export interface Device {
  ip: string;
  mac: string;
}

export const getConfig = callable<[], any>("get_config");
export const saveConfig = callable<[Config], any>("save_config");
export const wakePc = callable<[], any>("wake");
export const statusPc = callable<[], any>("status");
export const preflightPc = callable<[], any>("preflight");
export const testWake = callable<[], any>("test_wake");
export const testProbe = callable<[], any>("test_probe");
export const discover = callable<[], any>("discover");
export const getDiagnostics = callable<[], any>("get_diagnostics");
