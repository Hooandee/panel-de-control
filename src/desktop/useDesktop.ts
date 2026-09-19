import { useCallback, useEffect, useSyncExternalStore } from "react";

import {
  DesktopPowerMode,
  DesktopState,
  getDesktopState,
  retryDesktopMigration,
  setDesktopModeEnabled,
  setDesktopPowerLimits,
  setDesktopPowerMode,
} from "../api";

interface DesktopSnapshot {
  state: DesktopState | null;
  error: boolean;
}

let snapshot: DesktopSnapshot = { state: null, error: false };
let pending: Promise<void> | null = null;
let readGeneration = 0;
const listeners = new Set<() => void>();

function publish(next: DesktopSnapshot): void {
  snapshot = next;
  listeners.forEach((listener) => listener());
}

function invalidateDesktopRead(): void {
  readGeneration += 1;
  pending = null;
}

function publishWrite(state: DesktopState): void {
  invalidateDesktopRead();
  publish({ state, error: false });
}

function refreshAfterWrite(): Promise<void> {
  invalidateDesktopRead();
  return refreshDesktopState();
}

function refreshDesktopState(): Promise<void> {
  if (pending) return pending;
  const generation = readGeneration;
  pending = getDesktopState()
    .then((state) => {
      if (generation === readGeneration) publish({ state, error: false });
    })
    .catch(() => {
      if (generation === readGeneration) publish({ state: snapshot.state, error: true });
    })
    .finally(() => {
      if (generation === readGeneration) pending = null;
    });
  return pending;
}

export function ensureDesktopState(): void {
  if (!snapshot.state) void refreshDesktopState();
}

export function getDesktopSnapshot(): DesktopState | null {
  return snapshot.state;
}

export function subscribeDesktopState(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useDesktopState(poll = false) {
  const current = useSyncExternalStore(
    subscribeDesktopState,
    () => snapshot,
    () => snapshot,
  );

  useEffect(() => {
    ensureDesktopState();
    if (!poll) return;
    const timer = window.setInterval(refreshDesktopState, 1500);
    return () => window.clearInterval(timer);
  }, [poll]);

  const refresh = useCallback(() => { void refreshDesktopState(); }, []);
  const setEnabled = useCallback((enabled: boolean) => {
    setDesktopModeEnabled(enabled)
      .then(publishWrite)
      .catch(() => publish({ state: snapshot.state, error: true }));
  }, []);
  const applyMode = useCallback((mode: DesktopPowerMode) => {
    setDesktopPowerMode(mode)
      .then(refreshAfterWrite)
      .catch(() => publish({ state: snapshot.state, error: true }));
  }, []);
  const applyLimits = useCallback((cpu: number, gpu: number) => {
    setDesktopPowerLimits(cpu, gpu)
      .then(refreshAfterWrite)
      .catch(() => publish({ state: snapshot.state, error: true }));
  }, []);
  const retryMigration = useCallback(() => {
    retryDesktopMigration()
      .then(publishWrite)
      .catch(() => publish({ state: snapshot.state, error: true }));
  }, []);

  return { ...current, refresh, retryMigration, setEnabled, applyMode, applyLimits };
}
