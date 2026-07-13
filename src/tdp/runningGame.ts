import { Router } from "@decky/ui";
import { GameOverview, stableGameKey } from "./gameIdentity";

export interface RunningGame {
  /** Stable identity used as the per-game profile key everywhere (see gameIdentity.ts). */
  appid: string;
  name: string;
}

/**
 * Reads the foreground running game from Router.MainRunningApp.
 * Returns null when no game is running (Steam UI / desktop).
 * Never throws — wraps in try/catch for API unavailability.
 *
 * `appid` is the STABLE key from stableGameKey (a normalized name for non-Steam
 * shortcuts, the numeric appid for Steam games), so per-game profiles survive a
 * non-Steam shortcut's appid churn instead of being lost/clobbered on relaunch.
 *
 * Shared by the persistent game watcher (reports to the backend) and the
 * useRunningGame hook (local UI read only). See gameWatcher.ts for why the
 * backend report lives at plugin scope, not in the hook.
 */
export function readRunningGame(): RunningGame | null {
  try {
    const app = Router?.MainRunningApp as GameOverview | undefined;
    if (app && app.appid) {
      return {
        appid: stableGameKey(app),
        // `||` (not `??`) so a blank display_name falls back to the appid — an empty
        // name would hide the per-game scope tab (gated on a truthy game name).
        name: app.display_name || String(app.appid),
      };
    }
  } catch {
    /* API unavailable */
  }
  return null;
}
