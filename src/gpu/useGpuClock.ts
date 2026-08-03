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
  const [state, setState] = useState<GpuClockState | null>(null);
  const commit = useRef<ReturnType<typeof setTimeout> | null>(null);
  const stateRef = useRef<GpuClockState | null>(null);
  stateRef.current = state;
  const appid = game?.appid ?? null;
  const applyFollow = useCallback((follow: boolean, targetAppid: string) => {
    setGpuFollowGlobal(follow, targetAppid).then(setState).catch(() => {});
  }, []);
  const { scope, onScope } = useScopeSync(appid, state?.follows_global, applyFollow);
  const target = scope === "game" ? appid : null;

  // Re-fetch when the active scope changes so the card shows that scope's window.
  useEffect(() => {
    getGpuClock().then(setState).catch(() => {});
    return () => {
      if (commit.current) clearTimeout(commit.current);
    };
  }, [scope, appid]);

  const setManual = useCallback((manual: boolean) => {
    if (!manual) {
      if (commit.current) {
        clearTimeout(commit.current);
        commit.current = null;
      }
      setGpuClockAuto(scope, target).then(setState).catch(() => {});
      return;
    }
    // Turning manual ON: pin the current window (seed from the shown range).
    const cur = stateRef.current;
    if (!cur) return;
    setState({ ...cur, manual: true }); // optimistic
    setGpuClock(cur.min ?? cur.range_min ?? 0, cur.max ?? cur.range_max ?? 0, scope, target)
      .then(setState)
      .catch(() => {});
  }, [scope, target]);

  const setWindow = useCallback((min: number, max: number) => {
    setState((cur) => (cur ? { ...cur, manual: true, min, max } : cur)); // optimistic
    if (commit.current) clearTimeout(commit.current);
    commit.current = setTimeout(() => {
      setGpuClock(min, max, scope, target).then(setState).catch(() => {});
    }, 200);
  }, [scope, target]);

  return { state, scope, game, onScope, setManual, setWindow };
}
