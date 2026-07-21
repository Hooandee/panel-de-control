// Durable set of user-disabled module ids. localStorage cache (pdc:modules,
// auto-mirrored to the backend by pdcStorage → survives reboot, no first-paint
// flash) reconciled against the authoritative RPC on startup. Never throws.
import { useSyncExternalStore } from "react";
import { readString, writeString, onPrefsHealed } from "../system/pdcStorage";
import { getUiModules, setUiModule } from "../api";

const KEY = "pdc:modules";
const listeners = new Set<() => void>();
let cache: string[] | null = null;

function coerce(raw: string | null): string[] {
  if (!raw) return [];
  try {
    const v = JSON.parse(raw);
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

function read(): string[] {
  return coerce(readString(KEY));
}

/** Current user-disabled ids (stable reference until a change). */
export function getDisabled(): string[] {
  if (!cache) cache = read();
  return cache;
}

function commit(next: string[]): void {
  const sorted = [...new Set(next)].sort();
  if (JSON.stringify(sorted) === JSON.stringify(getDisabled())) return;
  cache = sorted;
  writeString(KEY, JSON.stringify(sorted));
  listeners.forEach((l) => l());
}

/** Optimistic toggle + authoritative RPC (backend routes power/learning + re-applies). */
export function setModuleDisabled(id: string, disabled: boolean): void {
  const cur = new Set(getDisabled());
  if (disabled) cur.add(id);
  else cur.delete(id);
  commit([...cur]);
  setUiModule(id, disabled)
    .then((r) => commit(r.disabled))
    .catch(() => {});
}

/** Re-enable every module (used by the editor reset). */
export function resetModules(): void {
  const ids = getDisabled();
  commit([]);
  ids.forEach((id) => setUiModule(id, false).catch(() => {}));
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
  cache = next;
  listeners.forEach((l) => l());
});

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

/** React binding: the disabled set as a Set (re-renders on any change). */
export function useModules(): Set<string> {
  const arr = useSyncExternalStore(subscribe, getDisabled, getDisabled);
  return new Set(arr);
}
