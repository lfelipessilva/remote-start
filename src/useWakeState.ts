import { useCallback, useEffect, useRef, useState } from "react";
import { ServerAPI, toaster } from "@decky/api";

export type State = "needs_setup" | "ready" | "checking" | "online" | "offline" | "waking" | "timed_out" | "error";

export interface Config { mac: string; broadcast: string; port: number; timeout: number; }
export interface Status { online: boolean; last_seen: string; }

export function useWakeState(serverApi: ServerAPI) {
  const [state, setState] = useState<State>("checking");
  const [config, setConfig] = useState<Config | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [lastChecked, setLastChecked] = useState<number>(Date.now());
  const [canWake, setCanWake] = useState<boolean>(true);
  const wakingRef = useRef<boolean>(false);
  const rateUntil = useRef<number>(0);
  const wakeCleanupRef = useRef<(() => void) | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r: any = await serverApi.callPluginMethod("get_config", {});
      const cfg = (r?.config ?? r) as Config;
      setConfig(cfg);
      if (!cfg || !cfg.mac) { setState("needs_setup"); return; }
      setState("checking");
      const st = await serverApi.callPluginMethod<Status>("status", {});
      setStatus(st);
      setLastChecked(Date.now());
      setState(st?.online ? "online" : "offline");
    } catch (e) {
      setState("error");
    }
  }, [serverApi]);

  useEffect(() => { refresh(); }, [refresh]);

  useEffect(() => () => { wakeCleanupRef.current?.(); }, []);

  useEffect(() => {
    const interval = state === "waking" ? 2000 : 5000;
    const id = setInterval(() => { refresh(); }, interval);
    return () => clearInterval(id);
  }, [state, refresh]);

  const wake = useCallback(async () => {
    if (Date.now() < rateUntil.current) return;
    rateUntil.current = Date.now() + 3000;
    setCanWake(false);
    setTimeout(() => setCanWake(true), 3000);
    wakingRef.current = true;
    setState("waking");
    let cancelled = false;
    try {
      await serverApi.callPluginMethod("wake", {});
      // polling handled by the 2s effect loop while state === "waking"
    } catch (e) {
      wakingRef.current = false;
      setState("error");
    }
  }, [serverApi, config]);

  return { state, config, status, lastChecked, wake, refresh, canWake, rateUntil };
}