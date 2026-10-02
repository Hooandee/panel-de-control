import { useSyncExternalStore } from "react";

import { onPrefsHealed, readString, writeString } from "../system/pdcStorage";
import { coerceKioskViewIds, KIOSK_VIEWS_KEY, toggleKioskView } from "./kioskViews";

const listeners = new Set<() => void>();
let cache: string[] | null = null;

function read(): string[] {
  try {
    const raw = readString(KIOSK_VIEWS_KEY);
    return raw ? coerceKioskViewIds(JSON.parse(raw)) : [];
  } catch {
    return [];
  }
}

export function getKioskViewIds(): string[] {
  if (!cache) cache = read();
  return cache;
}

export function setKioskViewChosen(id: string): void {
  cache = toggleKioskView(getKioskViewIds(), id);
  writeString(KIOSK_VIEWS_KEY, JSON.stringify(cache));
  listeners.forEach((l) => l());
}

onPrefsHealed(() => {
  const next = read();
  if (JSON.stringify(next) === JSON.stringify(getKioskViewIds())) return;
  cache = next;
  listeners.forEach((l) => l());
});

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

export function useKioskViewIds(): string[] {
  return useSyncExternalStore(subscribe, getKioskViewIds, getKioskViewIds);
}
