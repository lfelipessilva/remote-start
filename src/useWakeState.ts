import { useCallback, useEffect, useRef, useState } from "react";
import { ServerAPI } from "@decky/api";

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

  const refresh = useCallback(async () => {
    try {
      const cfg = await serverApi.callPluginMethod<Config>("get_config", {});
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

  useEffect(() => {
    const tick = () => { if (wakingRef.current) refresh(); };
    const id = setInterval(() => {
      if (wakingRef.current) refresh();
      else refresh();
    }, wakingRef.current ? 2000 : 5000);
    return () => clearInterval(id);
  }, [state, refresh]);

  const wake = useCallback(async () => {
    if (Date.now() < rateUntil.current) return;
    rateUntil.current = Date.now() + 3000;
    setCanWake(false);
    setTimeout(() => setCanWake(true), 3000);
    wakingRef.current = true;
    setState("waking");
    try {
      await serverApi.callPluginMethod("wake", {});
      // poll
      const start = Date.now();
      const iv = setInterval(async () => {
        const st = await serverApi.callPluginMethod<Status>("status", {});
        setStatus(st);
        setLastChecked(Date.now());
        if (st?.online) { clearInterval(iv); wakingRef.current = false; setState("online"); }
        else if (Date.now() - start > (config?.timeout ?? 30) * 1000) { clearInterval(iv); wakingRef.current = false; setState("timed_out"); }
      }, 2000);
    } catch (e) {
      wakingRef.current = false;
      setState("error");
    }
  }, [serverApi, config]);

  return { state, config, status, lastChecked, wake, refresh, canWake, rateUntil };
}