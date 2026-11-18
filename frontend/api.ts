import { callable } from "@decky/api";

export interface Config {
  alias: string;
  mac: string;
  ip: string;
  broadcast: string;
  ssh_user: string;
}

export interface Status {
  online: boolean;
  method: "ping" | "arp" | "none";
  latency_ms: number | null;
}

export interface Device {
  ip: string;
  mac: string;
  name?: string;
}

export const getConfig = callable<[], any>("get_config");
export const saveConfig = callable<[Config], any>("save_config");
export const wakePc = callable<[], any>("wake");
export const statusPc = callable<[], any>("status");
export const preflightPc = callable<[], any>("preflight");
export const discover = callable<[], any>("discover");
export const learnMac = callable<[], any>("learn_mac");
export const configureShutdown = callable<[string, string], any>("configure_shutdown");
export const shutdownPc = callable<[], any>("shutdown");
export const resetShutdownSetup = callable<[], any>("reset_shutdown_setup");
