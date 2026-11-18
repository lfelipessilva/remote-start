import { useCallback, useEffect, useRef, useState } from "react";
import { toaster } from "@decky/api";
import { useQuickAccessVisible } from "@decky/ui";
import { Config, Status, getConfig, wakePc, statusPc } from "./api";

export type State = "needs_setup" | "ready" | "checking" | "online" | "offline" | "waking" | "timed_out" | "error";

export function useWakeState() {
  const [state, setState] = useState<State>("checking");
  const [config, setConfig] = useState<Config | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [lastChecked, setLastChecked] = useState<number>(Date.now());
  const [canWake, setCanWake] = useState<boolean>(true);
  const wakingRef = useRef<boolean>(false);
  const wasWakingRef = useRef<boolean>(false);
  const rateUntil = useRef<number>(0);
  const wakeCleanupRef = useRef<(() => void) | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r: any = await getConfig();
      const cfg = (r?.config ?? r) as Config;
      setConfig(cfg);
      if (!cfg || !cfg.ip) { setState("needs_setup"); return; }
      if (!wakingRef.current) setState("checking");
      const st: any = await statusPc();
      setStatus(st);
      setLastChecked(Date.now());
      if (wakingRef.current && st?.online) {
        wakingRef.current = false;
        setState("online");
      } else if (!wakingRef.current) {
        setState(st?.online ? "online" : "offline");
      }
    } catch (e) {
      setState("error");
    }
  }, []);

  const visible = useQuickAccessVisible();
  useEffect(() => { if (visible) refresh(); }, [visible, refresh]);

  useEffect(() => () => { wakeCleanupRef.current?.(); }, []);

  useEffect(() => {
    if (state !== "waking") return;
    const id = setInterval(() => { refresh(); }, 2000);
    return () => clearInterval(id);
  }, [state, refresh]);

  useEffect(() => {
    if (wasWakingRef.current && state === "online") {
      toaster.toast({ title: "PC is online", body: "" });
    }
    if (wasWakingRef.current && state === "timed_out") {
      toaster.toast({ title: "No response after 2 min. Check power/WoL.", body: "" });
    }
    wasWakingRef.current = state === "waking";
  }, [state]);

  const wake = useCallback(async () => {
    if (Date.now() < rateUntil.current) return;
    rateUntil.current = Date.now() + 3000;
    setCanWake(false);
    setTimeout(() => setCanWake(true), 3000);
    wakingRef.current = true;
    setState("waking");
    const timeoutId = setTimeout(() => {
      if (wakingRef.current) { wakingRef.current = false; setState("timed_out"); }
    }, 120000);
    wakeCleanupRef.current = () => clearTimeout(timeoutId);
    try {
      const res: any = await wakePc();
      if (res?.error) {
        wakingRef.current = false;
        clearTimeout(timeoutId);
        setState("error");
        toaster.toast({ title: res.message ?? res.error, body: "" });
      }
    } catch (e) {
      wakingRef.current = false;
      clearTimeout(timeoutId);
      setState("error");
    }
  }, [config]);

  return { state, config, status, lastChecked, wake, refresh, canWake, rateUntil };
}