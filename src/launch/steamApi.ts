// Thin adapter over Steam's internal stores for launch options. The ONLY module
// here that touches @decky/window globals — the compose/catalog logic stays pure
// and testable. Everything is guarded: a missing global degrades to empty/no-op.

import { stableGameKey, gameInstanceKey, isNonSteam, APP_TYPE_TOOL } from "../tdp/gameIdentity";
import { recordUiEvent } from "../system/uiEvents";

export interface GameEntry {
  /** The exact numeric appid of the library entry opened by the user. */
  liveAppid: number;
  /** Stable identity (ns:name for shortcuts, numeric string for Steam games). */
  stableKey: string;
  /** Exact current library entry, used for UI preferences that must not merge shortcuts. */
  instanceKey: string;
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

/** Portrait candidates Steam resolved: the user's custom art (SteamGridDB / CSS
 *  Loader / "Set custom artwork") first, then the store capsule. Origin-relative
 *  custom URLs are absolutized. Empty → GameCover shows the fallback tile. */
export function resolveCoverUrls(ov: unknown): string[] {
  const abs = (u: string) => (u.startsWith("/") ? STEAM_UI_ORIGIN + u : u);
  const out: string[] = [];
  try {
    const store = w.appStore;
    // Several candidates (e.g. a stale JPG then a valid PNG) — keep all; GameCover falls through.
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
    instanceKey: gameInstanceKey(id),
    name: ov.display_name || String(ov.appid),
    isNonSteam: nonSteam,
    coverUrls: resolveCoverUrls(ov),
    lastPlayed: Number(ov.rt_last_time_played) || 0,
    playtime: Number(ov.minutes_playtime_forever) || 0,
  };
}

function isListedInstall(overview: Overview): boolean {
  return overview.app_type !== APP_TYPE_TOOL &&
    (isNonSteam(overview) || overview.local_per_client_data?.installed === true);
}

/** Installed Steam games + non-Steam shortcuts (order applied by the caller). Never throws. */
export function listInstalledGames(): GameEntry[] {
  try {
    const all: Overview[] = w.collectionStore?.allAppsCollection?.allApps ?? [];
    const out: GameEntry[] = [];
    for (const ov of all) {
      if (ov && typeof ov.appid === "number" && isListedInstall(ov)) out.push(overviewToEntry(ov));
    }
    return out;
  } catch {
    return [];
  }
}

function isPublicSteamGame(ov: Overview): boolean {
  return Number.isSafeInteger(ov.appid) && ov.appid > 0 && !isNonSteam(ov) &&
    (ov.app_type === 1 || ov.app_type === 8);
}

function lookupOverview(appid: number): Overview | undefined {
  const ov = w.appStore?.GetAppOverviewByAppID?.(appid);
  return ov?.appid === appid ? ov : undefined;
}

export interface SelectorSteamMetadata {
  appid: number;
  collection: boolean;
  local: "true" | "false" | "missing";
}

/** Complement Steam's installed flags with positive installer evidence for known games. */
export function readUpscalersSelection(confirmedAppids: readonly number[]) {
  const collection = new Map<number, Overview>();
  const unreadableIds = new Set<number>();
  let unreadableCollection = 0;
  try {
    const all: Overview[] = w.collectionStore?.allAppsCollection?.allApps ?? [];
    for (const ov of all) {
      try {
        const appid = ov?.appid;
        if (typeof appid === "number") collection.set(appid, ov);
      } catch {
        unreadableCollection++;
      }
    }
  } catch {
    unreadableCollection++;
  }
  const rows = new Map<number, { game: GameEntry; steam?: SelectorSteamMetadata }>();
  const addRow = (appid: number, ov: Overview, inCollection?: Overview) => {
    const game = overviewToEntry(ov);
    let steam: SelectorSteamMetadata | undefined;
    if (isPublicSteamGame(ov)) {
      const installed = (inCollection ?? ov).local_per_client_data?.installed;
      steam = { appid, collection: inCollection !== undefined,
        local: typeof installed === "boolean" ? installed ? "true" : "false" : "missing" };
    }
    rows.set(appid, { game, steam });
  };
  for (const [appid, ov] of collection) {
    try {
      if (isListedInstall(ov)) addRow(appid, ov, ov);
    } catch {
      unreadableIds.add(appid);
    }
  }
  let no_metadata = 0;
  let not_game = 0;
  for (const appid of new Set(confirmedAppids)) {
    if (!Number.isSafeInteger(appid) || appid <= 0 || appid >= 2 ** 31 || rows.get(appid)?.steam) continue;
    try {
      const inCollection = collection.get(appid);
      const ov = inCollection?.app_type === undefined ? lookupOverview(appid) ?? inCollection : inCollection;
      if (!ov || ov.app_type === undefined) {
        no_metadata++;
      } else if (!isPublicSteamGame(ov)) {
        not_game++;
      } else {
        addRow(appid, ov, inCollection);
      }
    } catch {
      unreadableIds.add(appid);
    }
  }
  const entries = [...rows.values()];
  const steam = entries.flatMap((row) => row.steam ? [row.steam] : []);
  const unreadable = unreadableCollection + unreadableIds.size;
  return { games: entries.map((row) => row.game), steam, no_metadata, not_game, unreadable };
}

/** Every game in the library, installed or not, plus non-Steam shortcuts; tools excluded. Ids and names only. Never throws. */
export function listLibraryGames(): { appId: number; name: string }[] {
  try {
    const all: Overview[] = w.collectionStore?.allAppsCollection?.allApps ?? [];
    const out: { appId: number; name: string }[] = [];
    for (const ov of all) {
      if (!ov || typeof ov.appid !== "number" || ov.app_type === APP_TYPE_TOOL) continue;
      out.push({ appId: ov.appid, name: ov.display_name || String(ov.appid) });
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

/** Read a game's launch options + compat tool together, preferring the details
 *  callback (fresh) over the often-empty/stale sync cache. Resolves NULL when
 *  nothing real could be read — callers must NOT treat that as an empty string. */
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
export function writeLaunchOptions(appid: number, value: string, isNonSteam = false, redactValue = false): boolean {
  try {
    const apps = w.SteamClient?.Apps;
    const setter =
      isNonSteam && typeof apps?.SetShortcutLaunchOptions === "function"
        ? apps.SetShortcutLaunchOptions
        : apps?.SetAppLaunchOptions;
    if (typeof setter !== "function") {
      recordUiEvent("launch", "set_options", { appid, nonSteam: isNonSteam, error: "no_setter" }, false);
      return false;
    }
    setter.call(apps, appid, value);
    recordUiEvent("launch", "set_options", { appid, nonSteam: isNonSteam, ...(redactValue ? { redacted: true } : { value: value.slice(0, 300) }) });
    return true;
  } catch (error) {
    recordUiEvent("launch", "set_options", { appid, nonSteam: isNonSteam, error: redactValue ? "setter_failed" : String(error).slice(0, 120) }, false);
    return false;
  }
}
