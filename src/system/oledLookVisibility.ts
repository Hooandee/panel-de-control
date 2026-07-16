import { useSyncExternalStore } from "react";

import { onPrefsHealed, readFlag, writeFlag } from "./pdcStorage";

const KEY = "pdc:oledLookCard:hidden";

let hidden = readFlag(KEY, false);
const listeners = new Set<() => void>();

function applyHidden(next: boolean): void {
  if (next === hidden) return;
  hidden = next;
  listeners.forEach((listener) => listener());
}

onPrefsHealed(() => applyHidden(readFlag(KEY, false)));

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function isOledLookCardHidden(): boolean {
  return hidden;
}

export function setOledLookCardHidden(next: boolean): void {
  writeFlag(KEY, next);
  applyHidden(next);
}

export function useOledLookCardHidden(): boolean {
  return useSyncExternalStore(subscribe, isOledLookCardHidden, isOledLookCardHidden);
}
