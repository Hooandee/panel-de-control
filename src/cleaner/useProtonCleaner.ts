import { useCallback, useEffect, useRef, useState } from "react";
import {
  cancelSteamCleaner,
  executeProtonCleaner,
  getProtonCleanerState,
  prepareProtonCleaner,
  scanProtonCleaner,
} from "../api";
import { cleanerErrorCode } from "./errors";
import type { ProtonResult, ProtonState } from "./protonTypes";

type ProtonOperation = "scan" | "clean";

export function useProtonCleaner() {
  const mounted = useRef(false);
  const epoch = useRef(0);
  const inflight = useRef<ProtonOperation | null>(null);
  const [state, setState] = useState<ProtonState | null>(null);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState<ProtonOperation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ProtonResult | null>(null);

  const refresh = useCallback(async () => {
    const revision = epoch.current;
    try {
      const next = await getProtonCleanerState();
      if (mounted.current && revision === epoch.current) {
        setState(next);
        setError(null);
      }
    } catch (failure) {
      if (mounted.current && revision === epoch.current) setError(cleanerErrorCode(failure));
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    void refresh();
    return () => {
      const shouldCancel = inflight.current !== null;
      mounted.current = false;
      epoch.current += 1;
      if (shouldCancel) void cancelSteamCleaner().catch(() => undefined);
    };
  }, [refresh]);

  const start = (operation: ProtonOperation) => {
    if (!mounted.current || inflight.current) return null;
    inflight.current = operation;
    setPending(operation);
    setError(null);
    setResult(null);
    return ++epoch.current;
  };

  const finish = (revision: number) => {
    inflight.current = null;
    if (mounted.current && revision === epoch.current) {
      setPending(null);
      setLoading(false);
    }
  };

  const scan = async () => {
    const revision = start("scan");
    if (revision === null) return;
    try {
      const next = await scanProtonCleaner();
      if (mounted.current && revision === epoch.current) setState(next);
    } catch (failure) {
      if (mounted.current && revision === epoch.current) setError(cleanerErrorCode(failure));
    } finally {
      finish(revision);
    }
  };

  const queueScan = useCallback(() => {
    if (!mounted.current || inflight.current) return;
    setLoading(true);
    setError(null);
    setResult(null);
  }, []);

  const clean = async (entryIds: string[]) => {
    if (!state?.scan_id || !entryIds.length) return;
    const revision = start("clean");
    if (revision === null) return;
    try {
      const plan = await prepareProtonCleaner(state.scan_id, entryIds);
      if (!mounted.current || revision !== epoch.current) return;
      const outcome = await executeProtonCleaner(plan.id);
      if (!mounted.current || revision !== epoch.current) return;
      setResult(outcome);
      const next = await getProtonCleanerState();
      if (mounted.current && revision === epoch.current) setState(next);
    } catch (failure) {
      if (mounted.current && revision === epoch.current) setError(cleanerErrorCode(failure));
    } finally {
      finish(revision);
    }
  };

  return {
    state,
    loading,
    pending,
    busy: loading || pending !== null,
    error,
    result,
    refresh,
    queueScan,
    scan,
    clean,
    dismissResult: () => setResult(null),
  };
}

export type ProtonCleanerController = ReturnType<typeof useProtonCleaner>;
