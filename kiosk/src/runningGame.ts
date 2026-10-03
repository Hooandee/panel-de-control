import { getKioskGame } from "../../src/api";
import { GameOverview, isNonSteamKey, nonSteamName } from "../../src/tdp/gameIdentity";

// Matches gameIdentity's shortcut detection so stableGameKey() hands back the same "ns:" key.
const APP_TYPE_SHORTCUT = 1073741824;
const SHORTCUT_APPID = 2147483648;

let current: GameOverview | undefined;

/** What Router.MainRunningApp would report inside Steam, rebuilt from the backend's current game. */
export function runningAppOverview(): GameOverview | undefined {
  return current;
}

export function overviewForKey(key: string | null | undefined, name: string | null): GameOverview | undefined {
  if (!key) return undefined;
  if (isNonSteamKey(key)) {
    return { appid: SHORTCUT_APPID, app_type: APP_TYPE_SHORTCUT, display_name: nonSteamName(key) };
  }
  return { appid: key, display_name: name ?? key };
}

const names: Record<string, string | null> = {};
const asked = new Set<string>();

/** Fed from the bottom screen's live poll (get_kiosk_live carries the backend's current game). */
export function noteRunningGame(key: string | null): void {
  if (key && !isNonSteamKey(key) && !asked.has(key)) {
    asked.add(key);
    void getKioskGame(key)
      .then((game) => {
        names[key] = game.name;
        if (current && String(current.appid) === key) current = overviewForKey(key, game.name);
      })
      .catch(() => asked.delete(key));
  }
  current = overviewForKey(key, key ? names[key] ?? null : null);
}
