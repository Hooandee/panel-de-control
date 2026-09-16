import { useSyncExternalStore } from "react";

import {
  onPrefsHealed,
  prefsHydrated,
  readFlag,
  readString,
  writeString,
} from "../system/pdcStorage";
import { coerceQamLayout, createDefaultQamLayout, type QamLayout } from "./layout";
import { migrateLegacyQamShortcut } from "./migration";

const KEY = "pdc:qamLayout";
const LEGACY_SHORTCUT_KEY = "pdc:qamShortcut";
const listeners = new Set<() => void>();
let cache: QamLayout | null = null;

function read(): QamLayout {
  try {
    const raw = readString(KEY);
    if (raw) return coerceQamLayout(JSON.parse(raw));
    const migrated = migrateLegacyQamShortcut(
      createDefaultQamLayout(),
      readFlag(LEGACY_SHORTCUT_KEY, true),
    );
    if (prefsHydrated()) writeString(KEY, JSON.stringify(migrated));
    return migrated;
  } catch {
    return createDefaultQamLayout();
  }
}

export function getQamLayout(): QamLayout {
  if (!cache) cache = read();
  return cache;
}

function publish(next: QamLayout): void {
  cache = next;
  listeners.forEach((listener) => listener());
}

export function saveQamLayout(next: QamLayout): void {
  writeString(KEY, JSON.stringify(next));
  publish(next);
}

export function resetQamLayout(): void {
  const next = createDefaultQamLayout();
  writeString(KEY, JSON.stringify(next));
  publish(next);
}

export function reloadQamLayout(): void {
  const next = read();
  if (JSON.stringify(next) !== JSON.stringify(getQamLayout())) publish(next);
}

export function subscribeQamLayout(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useQamLayout(): QamLayout {
  return useSyncExternalStore(subscribeQamLayout, getQamLayout, getQamLayout);
}

onPrefsHealed(reloadQamLayout);
