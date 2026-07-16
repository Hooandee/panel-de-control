// Thin adapter over Steam's internal stores for launch options. The ONLY module
// here that touches @decky/window globals — the compose/catalog logic stays pure
// and testable. Everything is guarded: a missing global degrades to empty/no-op.

import { stableGameKey, isNonSteam } from "../tdp/gameIdentity";

export interface GameEntry {
  /** The live numeric appid (a non-Steam shortcut's churns; resolve fresh at write). */
  liveAppid: number;
  /** Stable identity (ns:name for shortcuts, numeric string for Steam games). */
  stableKey: string;
  name: string;
  isNonSteam: boolean;
}

interface Overview {
  appid: number;
  display_name?: string;
  app_type?: number;
  local_per_client_data?: { installed?: boolean };
}

/* eslint-disable @typescript-eslint/no-explicit-any */
const w = window as any;

/** Installed Steam games + non-Steam shortcuts, sorted by name. Never throws. */
export function listInstalledGames(): GameEntry[] {
  try {
    const all: Overview[] = w.collectionStore?.allAppsCollection?.allApps ?? [];
    const out: GameEntry[] = [];
    for (const ov of all) {
      if (!ov || typeof ov.appid !== "number") continue;
      const id = { appid: ov.appid, display_name: ov.display_name, app_type: ov.app_type };
      const nonSteam = isNonSteam(id);
      // Non-Steam shortcuts are inherently local (they don't reliably populate the
      // installed flag); Steam games are listed only when actually installed.
      if (!nonSteam && ov.local_per_client_data?.installed !== true) continue;
      out.push({
        liveAppid: ov.appid,
        stableKey: stableGameKey(id),
        name: ov.display_name || String(ov.appid),
        isNonSteam: nonSteam,
      });
    }
    out.sort((a, b) => a.name.localeCompare(b.name));
    return out;
  } catch {
    return [];
  }
}

/** Resolve a stable key back to the current numeric appid (shortcut appids churn). */
export function resolveLiveAppid(stableKey: string): number | null {
  const g = listInstalledGames().find((e) => e.stableKey === stableKey);
  return g ? g.liveAppid : null;
}

/** Synchronous cached read (null when app details aren't cached yet). Cheap —
 *  used to count active pills per row without registering for details. */
export function readLaunchOptionsSync(appid: number): string | null {
  try {
    const d = w.appDetailsStore?.GetAppDetails?.(appid);
    return d ? d.strLaunchOptions ?? "" : null;
  } catch {
    return null;
  }
}

/**
 * Read a game's launch-options string. App details may not be cached yet, so we
 * register for details (which fires the current value) and race it against a
 * sync read + a timeout. Always resolves (empty string worst case).
 */
export function readLaunchOptions(appid: number, timeoutMs = 1200): Promise<string> {
  return new Promise((resolve) => {
    let done = false;
    let unreg: { unregister?: () => void } | undefined;
    const finish = (v: string) => {
      if (done) return;
      done = true;
      try {
        unreg?.unregister?.();
      } catch {
        /* ignore */
      }
      resolve(v);
    };
    try {
      unreg = w.SteamClient?.Apps?.RegisterForAppDetails?.(appid, (d: { strLaunchOptions?: string }) =>
        finish(d?.strLaunchOptions ?? ""),
      );
      // If the callback fired synchronously during registration, `unreg` was still
      // undefined inside finish() — unregister now so the subscription can't leak.
      if (done) unreg?.unregister?.();
    } catch {
      /* ignore */
    }
    const sync = readLaunchOptionsSync(appid);
    if (sync !== null) finish(sync);
    setTimeout(() => finish(sync ?? ""), timeoutMs);
  });
}

/** Write a game's launch-options string (works for Steam and non-Steam). No-op if unavailable. */
export function writeLaunchOptions(appid: number, value: string): void {
  try {
    w.SteamClient?.Apps?.SetAppLaunchOptions?.(appid, value);
  } catch {
    /* ignore */
  }
}
