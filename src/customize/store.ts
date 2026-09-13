// Shared module state keeps the shell and modal's separate React roots in sync.
import { useSyncExternalStore } from "react";
import { Layout, coerceLayout, createDefaultLayout } from "./layout";
import { readString, writeString, removeString } from "../system/pdcStorage";

const KEY = "pdc:layout";
const EMPTY: Layout = createDefaultLayout();

let cache: Layout | null = null;
const listeners = new Set<() => void>();

function read(): Layout {
  try {
    const raw = readString(KEY);
    if (!raw) return EMPTY;
    const parsed = JSON.parse(raw);
    const layout = coerceLayout(parsed);
    const migrated = JSON.stringify(layout);
    if (migrated !== JSON.stringify(parsed)) writeString(KEY, migrated);
    return layout;
  } catch {
    return EMPTY;
  }
}

export function getLayout(): Layout {
  if (!cache) cache = read();
  return cache;
}

export function saveLayout(next: Layout): void {
  cache = next;
  writeString(KEY, JSON.stringify(next));
  listeners.forEach((l) => l());
}

export function resetLayout(): void {
  cache = EMPTY;
  removeString(KEY);
  listeners.forEach((l) => l());
}

export function reloadLayout(): void {
  const next = read();
  if (JSON.stringify(next) === JSON.stringify(getLayout())) return;
  cache = next;
  listeners.forEach((l) => l());
}

export function subscribeLayout(cb: () => void): () => void {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

export function useLayout(): Layout {
  return useSyncExternalStore(subscribeLayout, getLayout, getLayout);
}
