import { getUiPrefs, setUiPrefs } from "../api";
import { isDurableKey, planFollowBackend, planPrefsSync } from "./prefsSync";

// localStorage cache with a durable backend mirror. Only durable keys (see
// isDurableKey) are mirrored; ephemeral ones just pass through the cache.

// Keys the user wrote this session — the heal must not clobber them with a
// backend snapshot captured before the write.
const dirty = new Set<string>();
// When each key was last written here, so a follower sync never reverts a fresh write
// with a backend snapshot taken before it landed.
const writtenAt = new Map<string, number>();
const FOLLOW_GRACE_MS = 10_000;
// Re-apply hooks fired once the cache is healed (see hydratePrefs).
const healed = new Set<() => void>();

function mirror(key: string, value: string | null): void {
  if (!isDurableKey(key)) return;
  dirty.add(key);
  writtenAt.set(key, Date.now());
  void setUiPrefs({ [key]: value }).catch(() => {});
}

export function readString(key: string): string | null {
  try {
    return window.localStorage?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

export function writeString(key: string, value: string): void {
  try {
    window.localStorage?.setItem(key, value);
  } catch {}
  mirror(key, value);
}

export async function writeStringConfirmed(key: string, value: string): Promise<boolean> {
  const previous = readString(key);
  dirty.add(key);
  writtenAt.set(key, Date.now());
  try {
    window.localStorage?.setItem(key, value);
  } catch {}
  try {
    if (await setUiPrefs({ [key]: value })) return true;
  } catch {}
  dirty.delete(key);
  try {
    if (previous === null) window.localStorage?.removeItem(key);
    else window.localStorage?.setItem(key, previous);
  } catch {}
  return false;
}

export function removeString(key: string): void {
  try {
    window.localStorage?.removeItem(key);
  } catch {}
  mirror(key, null);
}

export function readFlag(key: string, fallback = false): boolean {
  const v = readString(key);
  return v == null ? fallback : v === "1";
}

export function writeFlag(key: string, on: boolean): void {
  writeString(key, on ? "1" : "0");
}

function managedLocal(): Record<string, string> {
  const out: Record<string, string> = {};
  try {
    const ls = window.localStorage;
    if (!ls) return out;
    for (let i = 0; i < ls.length; i++) {
      const k = ls.key(i);
      if (k && isDurableKey(k)) {
        const v = ls.getItem(k);
        if (v != null) out[k] = v;
      }
    }
  } catch {}
  return out;
}

/** Register a hook to run after the cache is healed (e.g. re-read a value that
 * may have rendered stale). Returns an unsubscribe. */
export function onPrefsHealed(cb: () => void): () => void {
  healed.add(cb);
  return () => healed.delete(cb);
}

let hydration: Promise<void> | null = null;
let hydrated = false;

/** True once the cache has been healed from the durable backend copy — lets a
 * caller tell "no saved value" apart from "backend not read yet". */
export function prefsHydrated(): boolean {
  return hydrated;
}

// Heal the localStorage cache from the durable backend copy. Shared promise:
// the plugin-scope startup and the i18n provider await the same round-trip.
let follower = false;

/** This surface only follows the backend copy (see followBackendPrefs). */
export function becomePrefsFollower(): void {
  follower = true;
}

export function hydratePrefs(): Promise<void> {
  if (follower) return followBackendPrefs().then(() => undefined);
  if (!hydration) hydration = doHydrate();
  return hydration;
}

/** Mirror the backend copy without ever pushing local keys up. For a second surface
 * (the kiosk) that follows what the QAM saves. Resolves false when the backend is
 * unreachable. */
export async function followBackendPrefs(now: () => number = Date.now): Promise<boolean> {
  let backend: Record<string, string>;
  try {
    backend = (await getUiPrefs()) ?? {};
  } catch {
    return false;
  }
  const fresh = (k: string) => now() - (writtenAt.get(k) ?? -Infinity) < FOLLOW_GRACE_MS;
  const { set, remove } = planFollowBackend(backend, managedLocal());
  let changed = false;
  try {
    const ls = window.localStorage;
    for (const [k, v] of Object.entries(set)) {
      if (fresh(k)) continue;
      ls?.setItem(k, v);
      changed = true;
    }
    for (const k of remove) {
      if (fresh(k)) continue;
      ls?.removeItem(k);
      changed = true;
    }
  } catch {}
  const first = !hydrated;
  hydrated = true;
  if (changed || first) {
    healed.forEach((cb) => {
      try {
        cb();
      } catch {}
    });
  }
  return true;
}

async function doHydrate(): Promise<void> {
  let backend: Record<string, string>;
  try {
    backend = await getUiPrefs();
  } catch {
    hydration = null; // transient failure (e.g. backend not ready) — allow a retry
    return;
  }
  const { heal, migrate } = planPrefsSync(backend ?? {}, managedLocal());
  for (const [k, v] of Object.entries(heal)) {
    if (dirty.has(k)) continue; // a fresh local write wins over the snapshot
    try {
      window.localStorage?.setItem(k, v);
    } catch {}
  }
  if (Object.keys(migrate).length) void setUiPrefs(migrate).catch(() => {});
  hydrated = true;
  healed.forEach((cb) => {
    try {
      cb();
    } catch {}
  });
}
