import { hydratePrefs, prefsHydrated, readFlag, writeFlag } from "./pdcStorage";

const KEY = "pdc:qamShortcut";

export interface QamShortcutSnapshot {
  enabled: boolean;
  appliedEnabled: boolean;
  registered: boolean;
  initialized: boolean;
  restartRequired: boolean;
}

interface QamShortcutRegistration {
  registered: boolean;
  dispose(): void;
}

export interface QamShortcutSession {
  ready: Promise<void>;
  dispose(): void;
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

export function startQamShortcut(
  register: () => QamShortcutRegistration,
  removeOwned: () => unknown,
  deactivate: () => void,
  supported: boolean,
): QamShortcutSession {
  let stopped = false;
  removeOwned();
  const startupEnabled = getQamShortcutEnabled();
  let registration = startupEnabled && supported ? register() : null;
  setQamShortcutRuntime(startupEnabled, registration?.registered === true);
  const ready = hydratePrefs().then(() => {
    if (stopped || !prefsHydrated()) return;
    refreshQamShortcutPreference();
    const nextEnabled = getQamShortcutEnabled();
    if (!nextEnabled) {
      deactivate();
      registration?.dispose();
      registration = null;
      removeOwned();
      setQamShortcutRuntime(false, false);
      return;
    }
    setQamShortcutRuntime(startupEnabled, registration?.registered === true);
  });

  return {
    ready,
    dispose() {
      if (stopped) return;
      stopped = true;
      registration?.dispose();
    },
  };
}
