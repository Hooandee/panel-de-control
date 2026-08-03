import { useCallback, useEffect, useRef, useState } from "react";
import {
  getGpuClock,
  setGpuClock,
  setGpuClockAuto,
  setGpuFollowGlobal,
  GpuClockState,
  TdpScope,
} from "../api";
import { useRunningGame } from "../tdp/useRunningGame";
import { useScopeSync } from "../useScopeSync";

export interface GpuClockControl {
  state: GpuClockState | null;
  scope: TdpScope;
  game: ReturnType<typeof useRunningGame>;
  onScope: (scope: TdpScope) => void;
  setManual: (manual: boolean) => void;
  setWindow: (min: number, max: number) => void;
}

/**
 * Owns the GPU-clock state. Loads once on mount; the min/max sliders commit with a
 * 200 ms debounce (optimistic local update); the Auto/Manual toggle is discrete
 * (returned state is source of truth). Never throws.
 */
export function useGpuClock(): GpuClockControl {
  const game = useRunningGame();
  const appid = game?.appid ?? null;
  const [state, setState] = useState<GpuClockState | null>(null);
  const commit = useRef<ReturnType<typeof setTimeout> | null>(null);
  const stateRef = useRef<GpuClockState | null>(null);
  const confirmedRef = useRef<GpuClockState | null>(null);
  const requestEpoch = useRef(0);
  const mutationPending = useRef(false);
  const contextAppid = useRef(appid);
  stateRef.current = state;
  const accept = useCallback((next: GpuClockState) => {
    confirmedRef.current = next;
    setState(next);
  }, []);
  const mutate = useCallback(async (request: () => Promise<GpuClockState>) => {
    const epoch = ++requestEpoch.current;
    mutationPending.current = true;
    try {
      const next = await request();
      if (epoch !== requestEpoch.current) return null;
      accept(next);
      return next;
    } catch {
      if (epoch !== requestEpoch.current) return null;
      setState(confirmedRef.current);
      try {
        const next = await getGpuClock();
        if (epoch !== requestEpoch.current) return null;
        accept(next);
        return next;
      } catch {
        return null;
      }
    } finally {
      if (epoch === requestEpoch.current) mutationPending.current = false;
    }
  }, [accept]);
  const applyFollow = useCallback(async (follow: boolean, targetAppid: string) => {
    const next = await mutate(() => setGpuFollowGlobal(follow, targetAppid));
    return next?.follows_global === follow;
  }, [mutate]);
  const { scope, onScope } = useScopeSync(appid, state?.follows_global, applyFollow);
  const target = scope === "game" ? appid : null;

  // Re-fetch when the active scope changes so the card shows that scope's window.
  useEffect(() => {
    const contextChanged = contextAppid.current !== appid;
    contextAppid.current = appid;
    if (mutationPending.current && !contextChanged) {
      return () => {
        if (commit.current) clearTimeout(commit.current);
      };
    }
    if (contextChanged) mutationPending.current = false;
    let alive = true;
    const epoch = ++requestEpoch.current;
    getGpuClock()
      .then((next) => {
        if (alive && epoch === requestEpoch.current) accept(next);
      })
      .catch(() => {});
    return () => {
      alive = false;
      if (commit.current) clearTimeout(commit.current);
    };
  }, [scope, appid, accept]);

  const setManual = useCallback((manual: boolean) => {
    if (!manual) {
      if (commit.current) {
        clearTimeout(commit.current);
        commit.current = null;
      }
      mutate(() => setGpuClockAuto(scope, target, appid));
      return;
    }
    // Turning manual ON: pin the current window (seed from the shown range).
    const cur = stateRef.current;
    if (!cur) return;
    setState({ ...cur, manual: true }); // optimistic
    mutate(() => setGpuClock(
      cur.min ?? cur.range_min ?? 0,
      cur.max ?? cur.range_max ?? 0,
      scope,
      target,
      appid,
    ));
  }, [appid, mutate, scope, target]);

  const setWindow = useCallback((min: number, max: number) => {
    setState((cur) => (cur ? { ...cur, manual: true, min, max } : cur)); // optimistic
    if (commit.current) clearTimeout(commit.current);
    commit.current = setTimeout(() => {
      commit.current = null;
      mutate(() => setGpuClock(min, max, scope, target, appid));
    }, 200);
  }, [appid, mutate, scope, target]);

  return { state, scope, game, onScope, setManual, setWindow };
}
