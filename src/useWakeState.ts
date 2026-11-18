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
      const start = Date.now();
      const iv = setInterval(async () => {
        if (cancelled) { clearInterval(iv); return; }
        const st = await serverApi.callPluginMethod<Status>("status", {});
        if (cancelled) { clearInterval(iv); return; }
        setStatus(st);
        setLastChecked(Date.now());
        if (st?.online) { clearInterval(iv); wakingRef.current = false; setState("online"); toaster.toast({ title: `${config?.mac ?? "PC"} is online` }); }
        else if (Date.now() - start > (config?.timeout ?? 30) * 1000) { clearInterval(iv); wakingRef.current = false; setState("timed_out"); toaster.toast({ title: "No response after 2 min..." }); }
      }, 2000);
      // unmount guard
      const cleanup = () => { cancelled = true; clearInterval(iv); };
      wakeCleanupRef.current = cleanup;
    } catch (e) {
      wakingRef.current = false;
      setState("error");
    }
  }, [serverApi, config]);

  return { state, config, status, lastChecked, wake, refresh, canWake, rateUntil };
}