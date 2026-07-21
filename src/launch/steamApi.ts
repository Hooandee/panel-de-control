// Thin adapter over Steam's internal stores for launch options. The ONLY module
// here that touches @decky/window globals — the compose/catalog logic stays pure
// and testable. Everything is guarded: a missing global degrades to empty/no-op.

import { stableGameKey, isNonSteam, APP_TYPE_TOOL } from "../tdp/gameIdentity";

export interface GameEntry {
  /** The live numeric appid (a non-Steam shortcut's churns; resolve fresh at write). */
  liveAppid: number;
  /** Stable identity (ns:name for shortcuts, numeric string for Steam games). */
  stableKey: string;
  name: string;
  isNonSteam: boolean;
  /** Vertical capsule (portrait) URL, or null → the fallback tile is used. */
  coverUrl: string | null;
  /** Unix seconds of last play (0 = never) — drives the default "recent" sort. */
  lastPlayed: number;
  /** Total minutes played forever — drives the "most played" sort. */
  playtime: number;
}

const STEAM_UI_ORIGIN = "https://steamloopback.host";

/** The portrait Steam already resolved, via its own asset store. Prefers the user's
 *  custom art when set (SteamGridDB / CSS Loader / "Set custom artwork") — this also
 *  gives non-Steam shortcuts a real cover — else the store vertical capsule. Custom
 *  URLs are origin-relative (/customimages/…); absolutize them. Null → fallback tile;
 *  a dead URL (e.g. a non-Steam shortcut with no art) fails to load → GameCover's
 *  onError shows the tile. `ov` is a live appStore overview. */
export function resolveCoverUrl(ov: unknown): string | null {
  try {
    const store = w.appStore;
    const custom = store?.GetCustomVerticalCapsuleURLs?.(ov);
    if (Array.isArray(custom) && typeof custom[0] === "string" && custom[0]) {
      return custom[0].startsWith("/") ? STEAM_UI_ORIGIN + custom[0] : custom[0];
    }
    const cap = store?.GetVerticalCapsuleURLForApp?.(ov);
    return typeof cap === "string" && cap ? cap : null;
  } catch {
    return null;
  }
}

interface Overview {
  appid: number;
  display_name?: string;
  app_type?: number;
  local_per_client_data?: { installed?: boolean };
  rt_last_time_played?: number;
  minutes_playtime_forever?: number;
}

/* eslint-disable @typescript-eslint/no-explicit-any */
const w = window as any;

/** Map a live appStore overview to a GameEntry. Shared by the section list and the
 *  library context menu so the entry shape lives in one place. */
export function overviewToEntry(ov: Overview): GameEntry {
  const id = { appid: ov.appid, display_name: ov.display_name, app_type: ov.app_type };
  const nonSteam = isNonSteam(id);
  return {
    liveAppid: ov.appid,
    stableKey: stableGameKey(id),
    name: ov.display_name || String(ov.appid),
    isNonSteam: nonSteam,
    coverUrl: resolveCoverUrl(ov),
    lastPlayed: Number(ov.rt_last_time_played) || 0,
    playtime: Number(ov.minutes_playtime_forever) || 0,
  };
}

/** Installed Steam games + non-Steam shortcuts (order applied by the caller). Never throws. */
export function listInstalledGames(): GameEntry[] {
  try {
    const all: Overview[] = w.collectionStore?.allAppsCollection?.allApps ?? [];
    const out: GameEntry[] = [];
    for (const ov of all) {
      if (!ov || typeof ov.appid !== "number") continue;
      // Tools (Proton builds, runtimes, redistributables) aren't games you set
      // launch options on — never list them.
      if (ov.app_type === APP_TYPE_TOOL) continue;
      // Non-Steam shortcuts are inherently local (they don't reliably populate the
      // installed flag); Steam games are listed only when actually installed.
      if (!isNonSteam(ov) && ov.local_per_client_data?.installed !== true) continue;
      out.push(overviewToEntry(ov));
    }
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
 * register for details (which fires the current value) and race it against a sync
 * read + a timeout. Resolves NULL when nothing real could be read (details not
 * cached and no callback by the timeout) — callers must NOT treat that as an empty
 * string, or a later write could erase the user's real options.
 */
export function readLaunchOptions(appid: number, timeoutMs = 1200): Promise<string | null> {
  return new Promise((resolve) => {
    let done = false;
    let unreg: { unregister?: () => void } | undefined;
    const finish = (v: string | null) => {
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
    // sync is null when details aren't cached → resolve null (unknown), not "".
    setTimeout(() => finish(sync), timeoutMs);
  });
}

/** The game's Proton compat tool (id + human label), from cached app details.
 *  Empty strings when unknown / native Linux / details not cached. */
export function readCompatTool(appid: number): { name: string; display: string } {
  try {
    const d = w.appDetailsStore?.GetAppDetails?.(appid);
    return { name: d?.strCompatToolName ?? "", display: d?.strCompatToolDisplayName ?? "" };
  } catch {
    return { name: "", display: "" };
  }
}

/** Write a game's launch-options string. Non-Steam shortcuts have their own setter.
 *  Returns false when no setter exists or the call throws — callers must not report
 *  success (or adopt the new baseline) unless this returns true. */
export function writeLaunchOptions(appid: number, value: string, isNonSteam = false): boolean {
  try {
    const apps = w.SteamClient?.Apps;
    const setter =
      isNonSteam && typeof apps?.SetShortcutLaunchOptions === "function"
        ? apps.SetShortcutLaunchOptions
        : apps?.SetAppLaunchOptions;
    if (typeof setter !== "function") return false;
    setter.call(apps, appid, value);
    return true;
  } catch {
    return false;
  }
}
