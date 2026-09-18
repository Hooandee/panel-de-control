import { useCallback, useEffect, useRef, useState } from "react";

import {
  composeSteamPerformanceRows,
  performanceLayoutFromStore,
  SteamPerformanceRow,
} from "./performanceSurface";
import {
  discoverSteamPerformanceComponents,
  resolveSteamPerformanceStore,
  subscribeSteamPerformanceState,
} from "./performanceRuntime";

export interface SteamPerformanceSurfaceState {
  status: "loading" | "ready" | "unavailable";
  rows: SteamPerformanceRow[];
}

const LOADING: SteamPerformanceSurfaceState = { status: "loading", rows: [] };
const EMPTY: SteamPerformanceSurfaceState = { status: "unavailable", rows: [] };
const RETRY_MS = 2000;

const sameRows = (left: SteamPerformanceRow[], right: SteamPerformanceRow[]): boolean => (
  left.length === right.length
  && left.every((row, index) => (
    row.id === right[index]?.id && row.Component === right[index]?.Component
  ))
);

const readSurface = (): SteamPerformanceSurfaceState => {
  const components = discoverSteamPerformanceComponents();
  const store = resolveSteamPerformanceStore();
  const layout = store ? performanceLayoutFromStore(store) : null;
  const rows = layout
    ? composeSteamPerformanceRows(components, layout)
    : [];
  return rows.some(({ id }) => id !== "profile" && id !== "reset")
    ? { status: "ready", rows }
    : EMPTY;
};

export function useSteamPerformanceSurface(): SteamPerformanceSurfaceState {
  const [surface, setSurface] = useState<SteamPerformanceSurfaceState>(LOADING);
  const aliveRef = useRef(false);

  const sync = useCallback(() => {
    if (!aliveRef.current) return;
    const next = readSurface();
    setSurface((previous) => (
      previous.status === next.status && sameRows(previous.rows, next.rows)
        ? previous
        : next
    ));
  }, []);

  useEffect(() => {
    aliveRef.current = true;
    const unsubscribe = subscribeSteamPerformanceState(sync);
    sync();
    const timer = setInterval(sync, RETRY_MS);
    return () => {
      aliveRef.current = false;
      clearInterval(timer);
      unsubscribe();
    };
  }, [sync]);

  return surface;
}
