// Customization layout store: a module singleton persisted in localStorage.
// The editor modal renders in a SEPARATE React root (showModal), so a plain
// module store + subscribe is what lets a save there re-render the shell and
// sections live. Never throws; degrades to defaults if storage is unavailable.
import { useSyncExternalStore } from "react";
import { Layout, coerceLayout } from "./layout";
import { readString, writeString, removeString } from "../system/pdcStorage";

const KEY = "pdc:layout";
const EMPTY: Layout = { tabs: { order: [], hidden: [] }, blocks: {}, subitems: {} };

// Layout is treated as IMMUTABLE: saveLayout/resetLayout always assign a fresh
// object (never mutate in place), so useSyncExternalStore sees a new reference
// exactly when — and only when — something changed.
let cache: Layout | null = null;
const listeners = new Set<() => void>();

function read(): Layout {
  try {
    const raw = readString(KEY);
    if (!raw) return EMPTY;
    // Coerce shapes: valid JSON with wrong types (e.g. order:5) must NOT throw
    // downstream — that would brick the panel with no in-UI recovery path.
    return coerceLayout(JSON.parse(raw));
  } catch {
    return EMPTY;
  }
}

/** Current layout (cached; stable reference until save/reset so useSyncExternalStore is happy). */
export function getLayout(): Layout {
  if (!cache) cache = read();
  return cache;
}

export function saveLayout(next: Layout): void {
  cache = next;
  writeString(KEY, JSON.stringify(next));
  listeners.forEach((l) => l());
}

/** Wipe all customization → back to code defaults. */
export function resetLayout(): void {
  cache = EMPTY;
  removeString(KEY);
  listeners.forEach((l) => l());
}

// Re-read once hydratePrefs heals the cache; notify only if it changed.
export function reloadLayout(): void {
  const next = read();
  if (JSON.stringify(next) === JSON.stringify(getLayout())) return;
  cache = next;
  listeners.forEach((l) => l());
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

/** React binding: re-renders on any save/reset, across React roots. */
export function useLayout(): Layout {
  return useSyncExternalStore(subscribe, getLayout, getLayout);
}
