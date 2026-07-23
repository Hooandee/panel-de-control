import { useSyncExternalStore } from "react";
import { readString, writeString, onPrefsHealed } from "../system/pdcStorage";
import { CustomView, DEFAULT_VIEW_ICON, ViewIconKey, coerceViews } from "./views";

const KEY = "pdc:views";
const SEQ_KEY = "pdc:views:seq";
const listeners = new Set<() => void>();
let cache: CustomView[] | null = null;

function read(): CustomView[] {
  try {
    const raw = readString(KEY);
    return raw ? coerceViews(JSON.parse(raw)) : [];
  } catch {
    return [];
  }
}

export function getViews(): CustomView[] {
  if (!cache) cache = read();
  return cache;
}

function commit(next: CustomView[]): void {
  cache = next;
  writeString(KEY, JSON.stringify(next));
  listeners.forEach((l) => l());
}

function nextId(): string {
  try {
    const c = (globalThis as { crypto?: { randomUUID?: () => string } }).crypto;
    if (c?.randomUUID) return c.randomUUID();
  } catch {
    /* fall through */
  }
  const n = Number(readString(SEQ_KEY) ?? "0") + 1;
  writeString(SEQ_KEY, String(n));
  return `v${n}`;
}

export function createView(name: string): string {
  const id = nextId();
  commit([...getViews(), { id, name, icon: DEFAULT_VIEW_ICON, blocks: [] }]);
  return id;
}

function update(id: string, patch: (v: CustomView) => CustomView): void {
  commit(getViews().map((v) => (v.id === id ? patch(v) : v)));
}

export const renameView = (id: string, name: string): void => update(id, (v) => ({ ...v, name }));
export const setViewIcon = (id: string, icon: ViewIconKey): void => update(id, (v) => ({ ...v, icon }));
export const setViewBlocks = (id: string, blocks: string[]): void =>
  update(id, (v) => ({ ...v, blocks: [...blocks] }));

export function deleteView(id: string): void {
  commit(getViews().filter((v) => v.id !== id));
}

onPrefsHealed(() => {
  const next = read();
  if (JSON.stringify(next) === JSON.stringify(getViews())) return;
  cache = next;
  listeners.forEach((l) => l());
});

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

export function useViews(): CustomView[] {
  return useSyncExternalStore(subscribe, getViews, getViews);
}
