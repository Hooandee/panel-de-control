import { readFlag, writeFlag } from "./pdcStorage";

const KEY = "pdc:qamShortcut";

export interface QamShortcutSnapshot {
  enabled: boolean;
  appliedEnabled: boolean;
  registered: boolean;
  initialized: boolean;
  restartRequired: boolean;
}

const listeners = new Set<() => void>();
let enabled = readFlag(KEY, true);
let appliedEnabled = enabled;
let registered = false;
let initialized = false;
let snapshot = buildSnapshot();

function buildSnapshot(): QamShortcutSnapshot {
  return {
    enabled,
    appliedEnabled,
    registered,
    initialized,
    restartRequired: initialized && enabled !== appliedEnabled,
  };
}

function publish(): void {
  snapshot = buildSnapshot();
  listeners.forEach((listener) => listener());
}

export function getQamShortcutEnabled(): boolean {
  return readFlag(KEY, true);
}

export function setQamShortcutEnabled(next: boolean): void {
  if (enabled === next) return;
  enabled = next;
  writeFlag(KEY, next);
  publish();
}

export function refreshQamShortcutPreference(): void {
  const next = getQamShortcutEnabled();
  if (enabled === next) return;
  enabled = next;
  publish();
}

export function setQamShortcutRuntime(nextAppliedEnabled: boolean, nextRegistered: boolean): void {
  appliedEnabled = nextAppliedEnabled;
  registered = nextRegistered;
  initialized = true;
  publish();
}

export function getQamShortcutSnapshot(): QamShortcutSnapshot {
  return snapshot;
}

export function subscribeQamShortcut(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
