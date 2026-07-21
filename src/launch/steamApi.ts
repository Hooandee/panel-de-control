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
  /** Vertical capsule (portrait) URL candidates, tried in order; empty → fallback tile. */
  coverUrls: string[];
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
export function resolveCoverUrls(ov: unknown): string[] {
  const abs = (u: string) => (u.startsWith("/") ? STEAM_UI_ORIGIN + u : u);
  const out: string[] = [];
  try {
    const store = w.appStore;
    // Custom art can yield several candidates (e.g. a stale JPG then a valid PNG);
    // keep them all so GameCover can fall through to the one that loads.
    const custom = store?.GetCustomVerticalCapsuleURLs?.(ov);
    if (Array.isArray(custom)) for (const u of custom) if (typeof u === "string" && u) out.push(abs(u));
    const cap = store?.GetVerticalCapsuleURLForApp?.(ov);
    if (typeof cap === "string" && cap) out.push(abs(cap));
  } catch {
    /* ignore */
  }
  return out;
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
    coverUrls: resolveCoverUrls(ov),
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

export interface AppDetails {
  launch: string;
  /** Proton compat tool id + human label ("" when native / none). */
  compatName: string;
  compatDisplay: string;
}

function detailsOf(d: {
  strLaunchOptions?: string;
  strCompatToolName?: string;
  strCompatToolDisplayName?: string;
}): AppDetails {
  return {
    launch: d?.strLaunchOptions ?? "",
    compatName: d?.strCompatToolName ?? "",
    compatDisplay: d?.strCompatToolDisplayName ?? "",
  };
}

/**
 * Read a game's launch options AND compat tool together. Steam's details store is
 * often empty on open, so we register for details (fires the current value) and
 * PREFER that callback; the cached sync read is only a timeout fallback (a stale
 * cache must not beat a fresh callback). Resolves NULL when nothing real could be
 * read — callers must NOT treat that as empty (a write from "" would erase options).
 */
export function readAppDetails(appid: number, timeoutMs = 1200): Promise<AppDetails | null> {
  return new Promise((resolve) => {
    let done = false;
    let unreg: { unregister?: () => void } | undefined;
    const finish = (v: AppDetails | null) => {
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
      unreg = w.SteamClient?.Apps?.RegisterForAppDetails?.(appid, (d: Parameters<typeof detailsOf>[0]) =>
        finish(detailsOf(d)),
      );
      if (done) unreg?.unregister?.();
    } catch {
      /* ignore */
    }
    setTimeout(() => {
      try {
        const d = w.appDetailsStore?.GetAppDetails?.(appid);
        finish(d ? detailsOf(d) : null);
      } catch {
        finish(null);
      }
    }, timeoutMs);
  });
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
