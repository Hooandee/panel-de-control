// Durable set of user-disabled module ids. localStorage cache (pdc:modules,
// auto-mirrored to the backend by pdcStorage → survives reboot, no first-paint
// flash) reconciled against the authoritative RPC on startup. Never throws.
import { useMemo, useSyncExternalStore } from "react";
import { readString, writeString, onPrefsHealed } from "../system/pdcStorage";
import { strArray } from "./layout";
import { getUiModules, setUiModule, resetUiModules } from "../api";

const KEY = "pdc:modules";
const listeners = new Set<() => void>();
let cache: string[] | null = null;

function read(): string[] {
  const raw = readString(KEY);
  if (!raw) return [];
  try {
    return strArray(JSON.parse(raw));
  } catch {
    return [];
  }
}

/** Set cache + notify subscribers (no persistence — callers persist as needed). */
function emit(next: string[]): void {
  cache = next;
  listeners.forEach((l) => l());
}

/** Current user-disabled ids (stable reference until a change). */
export function getDisabled(): string[] {
  if (!cache) cache = read();
  return cache;
}

function commit(next: string[]): void {
  const sorted = [...new Set(next)].sort();
  if (JSON.stringify(sorted) === JSON.stringify(getDisabled())) return;
  writeString(KEY, JSON.stringify(sorted));
  emit(sorted);
}

/** Optimistic toggle + authoritative RPC (backend routes power/learning + re-applies). */
export function setModuleDisabled(id: string, disabled: boolean): void {
  const cur = new Set(getDisabled());
  if (disabled) cur.add(id);
  else cur.delete(id);
  commit([...cur]);
  setUiModule(id, disabled)
    .then((r) => commit(r.disabled))
    .catch(() => hydrateModules()); // RPC failed → reconcile with the backend truth
}

/** Re-enable every module (used by the editor reset). One authoritative RPC so
 *  there's no per-id response race and only a single backend re-apply. */
export function resetModules(): void {
  commit([]);
  resetUiModules()
    .then((r) => commit(r.disabled))
    .catch(() => hydrateModules()); // RPC failed → reconcile with the backend truth
}

/** Fetch the authoritative set once at startup and reconcile the cache. */
export function hydrateModules(): void {
  getUiModules()
    .then((r) => commit(r.disabled))
    .catch(() => {});
}

// Re-read the healed localStorage cache once the durable mirror lands.
onPrefsHealed(() => {
  const next = read();
  if (JSON.stringify(next) === JSON.stringify(getDisabled())) return;
  emit(next); // no writeString — the value came from the backend, don't echo it back
});

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

/** React binding: the disabled set as a Set (re-renders on any change). The
 *  array snapshot is stable across renders, so the Set is built once per change. */
export function useModules(): Set<string> {
  const arr = useSyncExternalStore(subscribe, getDisabled, getDisabled);
  return useMemo(() => new Set(arr), [arr]);
}
