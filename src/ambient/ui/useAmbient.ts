import { useSyncExternalStore } from "react";

import type { AmbientRuntime, AmbientSnapshot } from "../steam/runtime";

let active: AmbientRuntime | null = null;
const hostListeners = new Set<() => void>();

export function setAmbientRuntime(runtime: AmbientRuntime | null): void {
  active = runtime;
  for (const listener of hostListeners) listener();
}

export function ambientRuntime(): AmbientRuntime | null {
  return active;
}

function subscribe(listener: () => void): () => void {
  hostListeners.add(listener);
  const off = active?.subscribe(() => listener());
  return () => {
    hostListeners.delete(listener);
    off?.();
  };
}

export function useAmbient(): { runtime: AmbientRuntime | null; snapshot: AmbientSnapshot | null } {
  const snapshot = useSyncExternalStore(subscribe, () => active?.getSnapshot() ?? null);
  return { runtime: active, snapshot };
}
