import { useCallback, useEffect, useRef, useState } from "react";

import {
  composeSteamPerformanceRows,
  performanceLayoutFromStore,
  SteamPerformanceRow,
} from "./performanceSurface";
import {
  discoverSteamPerformanceComponents,
  resolveSteamPerformanceStore,
  readSteamPerformanceProfile,
  SteamPerformanceProfile,
  subscribeSteamPerformanceState,
} from "./performanceRuntime";
import { recordSteamPerformanceDiagnostic } from "./performanceDiagnostics";

export interface SteamPerformanceSurfaceState {
  status: "loading" | "ready" | "unavailable";
  rows: SteamPerformanceRow[];
  profile: SteamPerformanceProfile;
}

interface ObservedSurface extends SteamPerformanceSurfaceState {
  runningGameId: number | null;
}

const LOADING: ObservedSurface = { status: "loading", rows: [], profile: "unknown", runningGameId: null };
const RETRY_MS = 2000;

const sameRows = (left: SteamPerformanceRow[], right: SteamPerformanceRow[]): boolean => (
  left.length === right.length
  && left.every((row, index) => (
    row.id === right[index]?.id && row.Component === right[index]?.Component
  ))
);

const readSurface = (runningGameId: number | null): ObservedSurface => {
  const profile = readSteamPerformanceProfile(runningGameId);
  const components = discoverSteamPerformanceComponents();
  const store = resolveSteamPerformanceStore();
  const layout = store ? performanceLayoutFromStore(store) : null;
  const rows = layout
    ? composeSteamPerformanceRows(components, layout)
    : [];
  const ready = rows.some(({ id }) => id !== "reset");
  recordSteamPerformanceDiagnostic("surface", {
    status: ready ? "ready" : "unavailable",
    profile,
    running_game_id: runningGameId === null ? null : String(runningGameId),
    store_available: store !== null,
    layout_available: layout !== null,
    frame_rate_path: layout?.frameRate ?? null,
    split_scaling: layout?.splitScaling ?? null,
    row_ids: ready ? rows.map(({ id }) => id) : [],
  });
  return ready
    ? { status: "ready", rows, profile, runningGameId }
    : { status: "unavailable", rows: [], profile, runningGameId };
};

export function useSteamPerformanceSurface(
  _profileScope: "global" | "game" = "global",
  runningGameId: number | null = null,
): SteamPerformanceSurfaceState {
  const [surface, setSurface] = useState<ObservedSurface>(LOADING);
  const aliveRef = useRef(false);

  const sync = useCallback(() => {
    if (!aliveRef.current) return;
    const next = readSurface(runningGameId);
    setSurface((previous) => (
      previous.runningGameId === next.runningGameId
      && previous.status === next.status && previous.profile === next.profile && sameRows(previous.rows, next.rows)
        ? previous
        : next
    ));
  }, [runningGameId]);

  useEffect(() => {
    aliveRef.current = true;
    const refresh = () => sync();
    const unsubscribe = subscribeSteamPerformanceState(refresh);
    sync();
    const timer = setInterval(refresh, RETRY_MS);
    return () => {
      aliveRef.current = false;
      clearInterval(timer);
      unsubscribe();
    };
  }, [sync]);

  return {
    status: surface.status,
    rows: surface.rows,
    profile: surface.runningGameId === runningGameId ? surface.profile : "unknown",
  };
}
