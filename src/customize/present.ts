// Which block ids a section actually rendered (non-null) on THIS machine/config,
// reported by SectionBlocks. Lets the shell and editor reflect what the device
// really has instead of every block the manifest could show — a machine that
// can't configure a block never offers it, and a tab that renders nothing hides
// itself. Persisted (pdc:present, durable-mirrored) so the editor knows a
// section's real blocks after the first-ever visit, and self-heals each render.
// Groundwork for the global block registry (custom views).
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

/** Record the block ids a section rendered (order-insensitive → no churn). */
export function markPresent(sectionId: string, ids: string[]): void {
  const next = [...ids].sort();
  const cur = state()[sectionId];
  if (cur && cur.length === next.length && cur.every((x, i) => x === next[i])) return;
  cache = { ...state(), [sectionId]: next };
  writeString(KEY, JSON.stringify(cache));
  notify();
}

/** Report a single block's presence (used by standalone block components that
 *  know their own availability). Additive over markPresent — no unmount reset, so
 *  the editor remembers a block after the first visit. */
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
