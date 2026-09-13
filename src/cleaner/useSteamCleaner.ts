import { useCallback, useEffect, useRef, useState } from "react";
import { cancelSteamCleaner, executeSteamCleaner, getSteamCleanerState, prepareSteamCleaner, scanSteamCleaner } from "../api";
import { cleanerErrorCode } from "./errors";
import type { CleanerPlan, CleanerResult, CleanerState } from "./types";

type Operation = "scan" | "prepare" | "execute";

export function useSteamCleaner() {
  const [state, setState] = useState<CleanerState | null>(null);
  const [plan, setPlan] = useState<CleanerPlan | null>(null);
  const [result, setResult] = useState<CleanerResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState<Operation | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const mounted = useRef(false);
  const epoch = useRef(0);
  const inflight = useRef<Operation | null>(null);
  const cancelPending = useRef(false);
  const dismissedResult = useRef<string | null>(null);

  const accept = useCallback((next: CleanerState) => {
    setState(next);
    if (next.last_result && inflight.current !== "execute" && inflight.current !== "prepare"
      && next.last_result.operation_id !== dismissedResult.current) setResult(next.last_result);
  }, []);

  const refresh = useCallback(async () => {
    const revision = epoch.current;
    try {
      const next = await getSteamCleanerState();
      if (mounted.current && revision === epoch.current) { accept(next); setError(null); }
    } catch (failure) {
      if (mounted.current && revision === epoch.current) setError(cleanerErrorCode(failure));
    } finally {
      if (mounted.current && revision === epoch.current) setLoading(false);
    }
  }, [accept]);

  useEffect(() => {
    mounted.current = true;
    void refresh();
    return () => { mounted.current = false; epoch.current += 1; };
  }, [refresh]);

  const serverBusy = state?.status === "scanning" || state?.status === "cleaning";
  const busy = pending !== null || serverBusy;

  useEffect(() => {
    if (!serverBusy && pending !== "scan" && pending !== "execute") return;
    let stopped = false;
    let failures = 0;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      const revision = epoch.current;
      try {
        const next = await getSteamCleanerState();
        if (!stopped && mounted.current && revision === epoch.current) { accept(next); failures = 0; }
      } catch (failure) {
        failures += 1;
        if (!stopped && mounted.current && revision === epoch.current) setError(cleanerErrorCode(failure));
      }
      if (!stopped && failures < 3) timer = setTimeout(poll, 800);
    };
    timer = setTimeout(poll, 800);
    return () => { stopped = true; clearTimeout(timer); };
  }, [serverBusy, pending, accept]);

  const dismissResult = () => {
    dismissedResult.current = result?.operation_id ?? state?.last_result?.operation_id ?? dismissedResult.current;
    setResult(null);
  };

  const start = (operation: Operation): boolean => {
    if (!mounted.current || inflight.current || serverBusy) return false;
    dismissResult();
    inflight.current = operation;
    epoch.current += 1;
    setPending(operation);
    setError(null);
    return true;
  };
  const finish = () => {
    inflight.current = null;
    if (mounted.current) { setPending(null); setLoading(false); }
  };

  const scan = async () => {
    if (!start("scan")) return;
    setPlan(null);
    try {
      const next = await scanSteamCleaner();
      if (mounted.current) { epoch.current += 1; accept(next); }
    } catch (failure) {
      if (mounted.current) setError(cleanerErrorCode(failure));
    } finally { finish(); }
  };

  const executePlan = async (prepared: CleanerPlan, confirmPrefixes: boolean) => {
    inflight.current = "execute";
    epoch.current += 1;
    setPending("execute");
    setPlan(null);
    setResult(null);
    const next = await executeSteamCleaner(prepared.id, confirmPrefixes);
    if (mounted.current) { epoch.current += 1; setResult(next); await refresh(); }
  };

  const prepare = async (entryIds: string[]) => {
    if (!state?.scan_id || !entryIds.length || !start("prepare")) return;
    setPlan(null);
    try {
      const next = await prepareSteamCleaner(state.scan_id, entryIds);
      if (!mounted.current) return;
      epoch.current += 1;
      if (next.requires_prefix_confirmation) setPlan(next);
      else await executePlan(next, false);
    } catch (failure) {
      if (mounted.current) setError(cleanerErrorCode(failure));
    } finally { finish(); }
  };

  const execute = async (confirmPrefixes: boolean) => {
    if (!plan || (plan.requires_prefix_confirmation && !confirmPrefixes) || !start("execute")) return;
    try {
      await executePlan(plan, confirmPrefixes);
    } catch (failure) {
      if (mounted.current) setError(cleanerErrorCode(failure));
    } finally { finish(); }
  };

  const cancel = async () => {
    if (cancelPending.current) return;
    cancelPending.current = true;
    setCancelling(true);
    try {
      const next = await cancelSteamCleaner();
      if (mounted.current) { epoch.current += 1; accept(next); }
    } catch (failure) {
      if (mounted.current) setError(cleanerErrorCode(failure));
    } finally {
      cancelPending.current = false;
      if (mounted.current) setCancelling(false);
    }
  };

  return { state, plan, result, error, loading, pending, busy, cancelling, scan, prepare, execute, cancel, refresh, dismissResult, dismissPlan: () => setPlan(null) };
}

export type CleanerController = ReturnType<typeof useSteamCleaner>;
