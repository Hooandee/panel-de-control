// Stable per-game identity used as the profile key for every scoped store
// (TDP / fans / color / CPU) and telemetry. Kept free of @decky/ui imports so
// it stays unit-testable (the running-app read lives in runningGame.ts).
//
// Steam games have a permanent numeric appid → key by it. Non-Steam shortcuts
// don't: their appid is crc32(exe+name) with the top bit set, so it changes
// whenever a re-import tool (Steam ROM Manager, EmuDeck) regenerates the
// shortcut or the exe/name changes, and the foreground can briefly report a
// child process's transient appid. Keying those by name instead survives that
// churn (the trade-off: renaming a shortcut starts a fresh profile).

export interface GameOverview {
  appid: string | number;
  display_name?: string;
  app_type?: number;
}

// Prefix stamped on the stable key of a non-Steam shortcut (keyed by name, not its
// churning appid). Encode + decode live together so the format has one owner.
export const NS_PREFIX = "ns:";

/** Whether a stored per-game key belongs to a non-Steam shortcut. */
export function isNonSteamKey(key: string): boolean {
  return key.startsWith(NS_PREFIX);
}

/** The stored (normalized) name from a non-Steam key. */
export function nonSteamName(key: string): string {
  return key.slice(NS_PREFIX.length);
}

// EAppType.Shortcut — the reliable non-Steam flag when the overview carries it.
const APP_TYPE_SHORTCUT = 1073741824;
// Non-Steam shortcut appids have the top bit set (>= 2^31); real Steam appids
// stay far below it. Used as a detector when app_type is absent at runtime.
const NONSTEAM_APPID_MIN = 2147483648;

export function normalizeGameName(name: string): string {
  return name.trim().toLowerCase().replace(/\s+/g, " ");
}

export function isNonSteam(overview: GameOverview): boolean {
  if (overview.app_type === APP_TYPE_SHORTCUT) return true;
  const n = Number(overview.appid);
  return Number.isFinite(n) && n >= NONSTEAM_APPID_MIN;
}

export function stableGameKey(overview: GameOverview): string {
  const rawAppid = String(overview.appid);
  if (isNonSteam(overview)) {
    const name = overview.display_name ? normalizeGameName(overview.display_name) : "";
    if (name) return NS_PREFIX + name;
    // No usable name → keep the raw appid (never worse than before).
  }
  return rawAppid;
}
