/**
 * Game controls Steam's own API lacks. `forceClose` is the last resort after `SteamClient.Apps.TerminateApp`
 * left a game in `RunningApps`: Panel sends SIGTERM, then SIGKILL, to that game's reaper tree only (never
 * Steam, its web helper or gamescope). It never rejects; "unavailable" means Panel could not be asked.
 * `pause` freezes the running game while the theme's menus are over it (game_freeze.py): the theme renews it while
 * they are, and Panel thaws it `ms` after the last renewal (3 s at most), when the theme goes or with `resume`.
 * `howLongToBeat` asks howlongtobeat.com through Panel (Steam's client cannot reach it): hours to finish the main
 * story, with extras and everything; null when the game is not there or the site cannot be reached.
 * `protonDb` asks protondb.com the same way: its tier for the game, null when nobody rated it or it is out of reach.
 */
export type ThemeForceCloseResult = "not_found" | "terminated" | "killed" | "failed" | "unavailable";

export interface ThemeHowLongToBeat {
  main: number | null;
  plus: number | null;
  complete: number | null;
}

export interface ThemeExtensionGamesAccess {
  // Absent where Panel cannot close a game by force (Windows): a theme then offers no "force close".
  forceClose?(appid: number | string): Promise<ThemeForceCloseResult>;
  // False when no game runs or nothing could be frozen.
  pause(ms: number): Promise<boolean>;
  resume(): Promise<void>;
  howLongToBeat(appid: number | string, name: string): Promise<ThemeHowLongToBeat | null>;
  protonDb(appid: number | string): Promise<ThemeProtonDb | null>;
}

export type ThemeProtonDbTier = "platinum" | "gold" | "silver" | "bronze" | "borked" | "native";

export interface ThemeProtonDb {
  tier: ThemeProtonDbTier;
  // How many reports the tier stands on.
  total: number | null;
}

export interface ThemeGamesBackend {
  forceClose?(appid: string): Promise<unknown>;
  pause?(appid: string, ms: number): Promise<unknown>;
  resume?(): Promise<unknown>;
  howLongToBeat?(appid: string, name: string): Promise<unknown>;
  protonDb?(appid: string): Promise<unknown>;
}

const PROTON_TIERS = new Set<string>(["platinum", "gold", "silver", "bronze", "borked", "native"]);

interface SteamGlobals {
  SteamUIStore?: { MainRunningAppID?: unknown };
}

// The game Steam has in front; a shortcut's id exceeds 2^53 and travels as a decimal string.
function runningAppId(): string | null {
  try {
    const appid = (globalThis as SteamGlobals).SteamUIStore?.MainRunningAppID;
    const id = typeof appid === "number" && Number.isSafeInteger(appid) && appid > 0 ? String(appid) : appid;
    return typeof id === "string" && /^[1-9]\d{0,19}$/.test(id) ? id : null;
  } catch {
    return null;
  }
}

function decimalAppId(appid: number | string): string | null {
  const id = typeof appid === "number" && Number.isSafeInteger(appid) && appid > 0 ? String(appid) : appid;
  return typeof id === "string" && /^[1-9]\d{0,19}$/.test(id) ? id : null;
}

function hoursOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value > 0 && value < 100_000 ? value : null;
}

const RESULTS = new Set<ThemeForceCloseResult>(["not_found", "terminated", "killed", "failed"]);

export function createThemeGamesAccess(backend: ThemeGamesBackend): Readonly<ThemeExtensionGamesAccess> {
  const close = backend.forceClose;
  const forceClose = close
    ? async (appid: number | string): Promise<ThemeForceCloseResult> => {
      // Shortcut game ids exceed 2^53, so they travel as decimal strings.
      const id = typeof appid === "number" && Number.isSafeInteger(appid) && appid > 0 ? String(appid) : appid;
      if (typeof id !== "string" || !/^[1-9]\d{0,19}$/.test(id)) return "failed";
      try {
        const reply = await close.call(backend, id);
        const result = typeof reply === "object" && reply !== null ? (reply as { result?: unknown }).result : undefined;
        return RESULTS.has(result as ThemeForceCloseResult) ? result as ThemeForceCloseResult : "failed";
      } catch {
        return "unavailable";
      }
    }
    : undefined;
  return Object.freeze({
    ...(forceClose ? { forceClose } : {}),
    async pause(ms: number): Promise<boolean> {
      const appid = runningAppId();
      if (!appid || !backend.pause || !Number.isFinite(ms) || ms <= 0) return false;
      try {
        return (await backend.pause(appid, Math.round(ms))) === true;
      } catch {
        return false;
      }
    },
    async resume(): Promise<void> {
      try {
        await backend.resume?.();
      } catch {
        // The backend thaws by itself.
      }
    },
    async howLongToBeat(appid: number | string, name: string): Promise<ThemeHowLongToBeat | null> {
      const id = decimalAppId(appid);
      if (!id || !backend.howLongToBeat || typeof name !== "string" || !name.trim()) return null;
      try {
        const reply = await backend.howLongToBeat(id, name.trim().slice(0, 200));
        if (typeof reply !== "object" || reply === null || (reply as { result?: unknown }).result !== "found") return null;
        const { main, plus, complete } = reply as Record<string, unknown>;
        const times = { main: hoursOrNull(main), plus: hoursOrNull(plus), complete: hoursOrNull(complete) };
        return times.main === null && times.plus === null && times.complete === null ? null : times;
      } catch {
        return null;
      }
    },
    async protonDb(appid: number | string): Promise<ThemeProtonDb | null> {
      const id = decimalAppId(appid);
      if (!id || !backend.protonDb) return null;
      try {
        const reply = await backend.protonDb(id);
        if (typeof reply !== "object" || reply === null) return null;
        const { result, tier, total } = reply as Record<string, unknown>;
        if (result !== "found" || typeof tier !== "string" || !PROTON_TIERS.has(tier)) return null;
        return { tier: tier as ThemeProtonDbTier, total: typeof total === "number" && Number.isSafeInteger(total) && total >= 0 ? total : null };
      } catch {
        return null;
      }
    },
  });
}
