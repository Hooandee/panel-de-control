import { useCallback, useEffect, useRef, useState } from "react";
import { getGpuClock, setGpuClock, setGpuClockAuto, GpuClockState, TdpScope } from "../api";

export interface GpuClockControl {
  state: GpuClockState | null;
  setManual: (manual: boolean) => void;
  setWindow: (min: number, max: number) => void;
}

/**
 * Owns the GPU-clock state. Loads once on mount; the min/max sliders commit with a
 * 200 ms debounce (optimistic local update); the Auto/Manual toggle is discrete
 * (returned state is source of truth). Never throws.
 */
export function useGpuClock(scope: TdpScope, appid: string | null): GpuClockControl {
  const [state, setState] = useState<GpuClockState | null>(null);
  const commit = useRef<ReturnType<typeof setTimeout> | null>(null);
  const stateRef = useRef<GpuClockState | null>(null);
  stateRef.current = state;
  // RPC target: game writes need the appid; global writes ignore it.
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

  return { state, setManual, setWindow };
}
