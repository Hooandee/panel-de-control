import { createThemeGamesAccess, type ThemeExtensionGamesAccess } from "../themes/runtime/gamesAccess";

// Windows has no SIGSTOP and Steam no pause of its own, so a theme that freezes the running game while its menus
// are over it (games.pause, as on Linux with game_freeze.py) asks the host: it keeps a lease, and the companion
// suspends the game's processes while the lease lasts and Big Picture is in front (GameFreezer.cs). The lease ends by
// itself MAX_MS after the last renewal, so a theme that stops or breaks never leaves the game frozen for long.
/** CDP binding the companion adds to SharedJSContext; calling it wakes the companion at once. */
export const GAME_PAUSE_BINDING = "pdcHostGamePause";
export const GAME_PAUSE_MAX_MS = 3000;
/** How long the companion takes at most to thaw once the lease ends: the binding wakes it at once, and it rereads
 * the lease every 250 ms while a game is frozen. */
export const GAME_THAW_MS = 350;

type PauseScope = typeof globalThis & { [GAME_PAUSE_BINDING]?: (payload: string) => void };

export interface HostGamePause {
  games: Readonly<ThemeExtensionGamesAccess>;
  /** The game the lease holds, while it lasts. */
  paused(now?: number): string | null;
  /** Ends the lease before Steam raises the game's window; how long the companion may take to thaw it, or 0. */
  thawForRaise(): number;
  dispose(): void;
}

export function installHostGamePause(scope: typeof globalThis, clock: () => number = Date.now): HostGamePause {
  const target = scope as PauseScope;
  let appid: string | null = null;
  let until = 0;
  const signal = () => {
    try {
      target[GAME_PAUSE_BINDING]?.(JSON.stringify({ appid, until }));
    } catch {
      // Without the binding the companion still reads the lease from the host's status.
    }
  };
  const release = () => {
    if (appid === null) return;
    appid = null;
    until = 0;
    signal();
  };
  // No forceClose: closing a game stays Steam's on Windows, so a theme offers no "force close" there.
  const games = createThemeGamesAccess({
    pause: async (id: string, ms: number) => {
      const now = clock();
      // A lease that lapsed starts again: the companion has already let the game go.
      const fresh = appid !== id || now >= until;
      appid = id;
      until = now + Math.max(0, Math.min(ms, GAME_PAUSE_MAX_MS));
      if (fresh) signal();
      return true;
    },
    resume: async () => release(),
  });
  return {
    games,
    paused(now = clock()) {
      return appid !== null && now < until ? appid : null;
    },
    thawForRaise() {
      // A lapsed lease has already been let go; it still waits, the companion may not have read it yet.
      const held = appid !== null;
      release();
      return held ? GAME_THAW_MS : 0;
    },
    dispose: release,
  };
}
