/**
 * Game controls Steam's own API lacks. `forceClose` is the last resort after `SteamClient.Apps.TerminateApp`
 * left a game in `RunningApps`: Panel sends SIGTERM, then SIGKILL, to that game's reaper tree only (never
 * Steam, its web helper or gamescope). It never rejects; "unavailable" means Panel could not be asked.
 */
export type ThemeForceCloseResult = "not_found" | "terminated" | "killed" | "failed" | "unavailable";

export interface ThemeExtensionGamesAccess {
  forceClose(appid: number | string): Promise<ThemeForceCloseResult>;
}

export interface ThemeGamesBackend {
  forceClose(appid: string): Promise<unknown>;
}

const RESULTS = new Set<ThemeForceCloseResult>(["not_found", "terminated", "killed", "failed"]);

export function createThemeGamesAccess(backend: ThemeGamesBackend): Readonly<ThemeExtensionGamesAccess> {
  return Object.freeze({
    async forceClose(appid: number | string): Promise<ThemeForceCloseResult> {
      // Shortcut game ids exceed 2^53, so they travel as decimal strings.
      const id = typeof appid === "number" && Number.isSafeInteger(appid) && appid > 0 ? String(appid) : appid;
      if (typeof id !== "string" || !/^[1-9]\d{0,19}$/.test(id)) return "failed";
      try {
        const reply = await backend.forceClose(id);
        const result = typeof reply === "object" && reply !== null ? (reply as { result?: unknown }).result : undefined;
        return RESULTS.has(result as ThemeForceCloseResult) ? result as ThemeForceCloseResult : "failed";
      } catch {
        return "unavailable";
      }
    },
  });
}
