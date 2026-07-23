// Block ids each section has on this machine, reported per block by the
// availability probes in SectionView; persisted (durable-mirrored) so the editor
// knows a section's real blocks before its first visit.
import { useSyncExternalStore } from "react";
import { readString, writeString, onPrefsHealed } from "../system/pdcStorage";

const KEY = "pdc:present";
const listeners = new Set<() => void>();
let cache: Record<string, string[]> | null = null;
let version = 0;

function load(): Record<string, string[]> {
  try {
    const raw = readString(KEY);
    if (!raw) return {};
    const v = JSON.parse(raw);
    if (!v || typeof v !== "object" || Array.isArray(v)) return {};
    const out: Record<string, string[]> = {};
    for (const [k, val] of Object.entries(v)) {
      if (Array.isArray(val)) out[k] = val.filter((x): x is string => typeof x === "string");
    }
    return out;
  } catch {
    return {};
  }
}

function state(): Record<string, string[]> {
  if (!cache) cache = load();
  return cache;
}

function notify(): void {
  version++;
  listeners.forEach((l) => l());
}

export function markBlockPresent(sectionId: string, id: string, present: boolean): void {
  const cur = state()[sectionId] ?? [];
  const has = cur.includes(id);
  if (present === has) return;
  const next = present ? [...cur, id].sort() : cur.filter((x) => x !== id);
  cache = { ...state(), [sectionId]: next };
  writeString(KEY, JSON.stringify(cache));
  notify();
}

/** The block ids known present for a section, or null if never seen. */
export function getPresent(sectionId: string): string[] | null {
  return state()[sectionId] ?? null;
}

// Re-read once the durable cache is healed on startup.
onPrefsHealed(() => {
  cache = load();
  notify();
});

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

/** Re-render a consumer whenever any section's present-set changes. */
export function usePresentVersion(): number {
  return useSyncExternalStore(subscribe, () => version, () => version);
}
