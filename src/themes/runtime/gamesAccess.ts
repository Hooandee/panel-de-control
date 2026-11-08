/**
 * Game controls Steam's own API lacks. `forceClose` is the last resort after `SteamClient.Apps.TerminateApp`
 * left a game in `RunningApps`: Panel sends SIGTERM, then SIGKILL, to that game's reaper tree only (never
 * Steam, its web helper or gamescope). It never rejects; "unavailable" means Panel could not be asked.
 * `pause` freezes the running game while the theme's menus are over it (game_freeze.py): the theme renews it while
 * they are, and Panel thaws it `ms` after the last renewal (3 s at most), when the theme goes or with `resume`.
 */
export type ThemeForceCloseResult = "not_found" | "terminated" | "killed" | "failed" | "unavailable";

export interface ThemeExtensionGamesAccess {
  // Absent where Panel cannot close a game by force (Windows): a theme then offers no "force close".
  forceClose?(appid: number | string): Promise<ThemeForceCloseResult>;
  // False when no game runs or nothing could be frozen.
  pause(ms: number): Promise<boolean>;
  resume(): Promise<void>;
}

export interface ThemeGamesBackend {
  forceClose?(appid: string): Promise<unknown>;
  pause?(appid: string, ms: number): Promise<unknown>;
  resume?(): Promise<unknown>;
}

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
  });
}
