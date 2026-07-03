import { useCallback, useEffect, useRef, useState } from "react";
import { getGpuClock, setGpuClock, setGpuClockAuto, GpuClockState } from "../api";

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
export function useGpuClock(): GpuClockControl {
  const [state, setState] = useState<GpuClockState | null>(null);
  const commit = useRef<ReturnType<typeof setTimeout> | null>(null);
  const stateRef = useRef<GpuClockState | null>(null);
  stateRef.current = state;

  useEffect(() => {
    getGpuClock().then(setState).catch(() => {});
    return () => {
      if (commit.current) clearTimeout(commit.current);
    };
  }, []);

  const setManual = useCallback((manual: boolean) => {
    if (!manual) {
      setGpuClockAuto().then(setState).catch(() => {});
      return;
    }
    // Turning manual ON: pin the current window (seed from the shown range).
    const cur = stateRef.current;
    if (!cur) return;
    setState({ ...cur, manual: true }); // optimistic
    setGpuClock(cur.min ?? cur.range_min ?? 0, cur.max ?? cur.range_max ?? 0)
      .then(setState)
      .catch(() => {});
  }, []);

  const setWindow = useCallback((min: number, max: number) => {
    setState((cur) => (cur ? { ...cur, manual: true, min, max } : cur)); // optimistic
    if (commit.current) clearTimeout(commit.current);
    commit.current = setTimeout(() => {
      setGpuClock(min, max).then(setState).catch(() => {});
    }, 200);
  }, []);

  return { state, setManual, setWindow };
}
