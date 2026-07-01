import { Router } from "@decky/ui";

export interface RunningGame {
  appid: string;
  name: string;
}

/**
 * Reads the foreground running game from Router.MainRunningApp.
 * Returns null when no game is running (Steam UI / desktop).
 * Never throws — wraps in try/catch for API unavailability.
 *
 * Shared by the persistent game watcher (reports to the backend) and the
 * useRunningGame hook (local UI read only). See gameWatcher.ts for why the
 * backend report lives at plugin scope, not in the hook.
 */
export function readRunningGame(): RunningGame | null {
  try {
    const app = Router?.MainRunningApp;
    if (app && app.appid) {
      return {
        appid: String(app.appid),
        name: app.display_name ?? String(app.appid),
      };
    }
  } catch {
    /* API unavailable */
  }
  return null;
}
