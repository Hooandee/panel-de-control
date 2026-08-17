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
  restartRequired?: boolean;
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
let runtimeRestartRequired = false;
let snapshot = buildSnapshot();

function buildSnapshot(): QamShortcutSnapshot {
  return {
    enabled,
    appliedEnabled,
    registered,
    initialized,
    restartRequired: runtimeRestartRequired || (initialized && enabled !== appliedEnabled),
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

export function setQamShortcutRuntime(
  nextAppliedEnabled: boolean,
  nextRegistered: boolean,
  nextRestartRequired = false,
): void {
  appliedEnabled = nextAppliedEnabled;
  registered = nextRegistered;
  runtimeRestartRequired = nextRestartRequired;
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
  register: (onRuntimeFailure: () => void) => QamShortcutRegistration,
  removeOwned: () => boolean,
): QamShortcutSession {
  let stopped = false;
  let runtimeFailed = false;
  const onRuntimeFailure = () => {
    if (stopped) return;
    runtimeFailed = true;
    registered = false;
    runtimeRestartRequired = true;
    initialized = true;
    publish();
  };
  const cleanupRestartRequired = removeOwned() === true;
  const startupEnabled = getQamShortcutEnabled();
  let registration = startupEnabled ? register(onRuntimeFailure) : null;
  setQamShortcutRuntime(
    startupEnabled,
    !runtimeFailed && registration?.registered === true,
    runtimeFailed || cleanupRestartRequired || registration?.restartRequired === true,
  );
  const ready = hydratePrefs().then(() => {
    if (stopped || !prefsHydrated()) return;
    refreshQamShortcutPreference();
    const nextEnabled = getQamShortcutEnabled();
    if (!nextEnabled) {
      registration?.dispose();
      registration = null;
      setQamShortcutRuntime(false, false, runtimeFailed || removeOwned() === true);
      return;
    }
    setQamShortcutRuntime(
      startupEnabled,
      !runtimeFailed && registration?.registered === true,
      runtimeFailed || cleanupRestartRequired || registration?.restartRequired === true,
    );
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
