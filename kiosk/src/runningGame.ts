import { getKioskGame, getTdpState } from "../../src/api";
import { GameOverview, isNonSteamKey, nonSteamName } from "../../src/tdp/gameIdentity";

// Matches gameIdentity's shortcut detection so stableGameKey() hands back the same "ns:" key.
const APP_TYPE_SHORTCUT = 1073741824;
const SHORTCUT_APPID = 2147483648;
const POLL_MS = 3000;

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

export function followRunningGame(): void {
  let names: Record<string, string | null> = {};
  const sync = async () => {
    try {
      const key = (await getTdpState()).appid;
      if (key && !isNonSteamKey(key) && !(key in names)) {
        names = { ...names, [key]: (await getKioskGame(key).catch(() => ({ name: null }))).name };
      }
      current = overviewForKey(key, key ? names[key] ?? null : null);
    } catch {
      /* keep the last known game until the backend answers again */
    }
  };
  void sync();
  window.setInterval(() => void sync(), POLL_MS);
}
