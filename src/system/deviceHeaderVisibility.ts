import { useSyncExternalStore } from "react";

import { onPrefsHealed, readFlag, writeFlag } from "./pdcStorage";

const KEY = "pdc:deviceHeader:hidden";

let hidden = readFlag(KEY, false);
const listeners = new Set<() => void>();

function applyHidden(next: boolean): void {
  if (next === hidden) return;
  hidden = next;
  listeners.forEach((listener) => listener());
}

// The backend preference mirror may restore a value after the first render.
// Re-read it and update every mounted React root when hydration completes.
onPrefsHealed(() => applyHidden(readFlag(KEY, false)));

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function isDeviceHeaderHidden(): boolean {
  return hidden;
}

export function setDeviceHeaderHidden(next: boolean): void {
  writeFlag(KEY, next);
  applyHidden(next);
}

export function useDeviceHeaderHidden(): boolean {
  return useSyncExternalStore(subscribe, isDeviceHeaderHidden, isDeviceHeaderHidden);
}
