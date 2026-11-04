import { readRunningGame } from "../tdp/runningGame";

const EXIT_TIMEOUT_MS = 30000;
const POLL_MS = 500;
// Steam needs a moment after the reaper exits before it accepts a new launch of the same game.
const SETTLE_MS = 1500;

interface SteamApps { TerminateApp?(gameId: string, force: boolean): void; RunGame?(gameId: string, launchOptions: string, unknown: number, source: number): void }
interface Overview { m_gameid?: string }

function steam(): { apps?: SteamApps; overview(appid: number): Overview | undefined } {
  const scope = globalThis as { SteamClient?: { Apps?: SteamApps }; appStore?: { GetAppOverviewByAppID?(appid: number): Overview } };
  return { apps: scope.SteamClient?.Apps, overview: (appid) => scope.appStore?.GetAppOverviewByAppID?.(appid) };
}

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Closes the running game the way Steam's own «Exit game» does and opens it again; false when it would not close. */
export async function restartGame(liveAppid: number): Promise<boolean> {
  const { apps, overview } = steam();
  if (!apps?.TerminateApp || !apps.RunGame) return false;
  // Shortcuts launch by their 64-bit game id, not by the 32-bit app id.
  const gameId = overview(liveAppid)?.m_gameid || String(liveAppid);
  apps.TerminateApp(gameId, false);
  const deadline = Date.now() + EXIT_TIMEOUT_MS;
  while (readRunningGame()?.liveAppid === liveAppid) {
    if (Date.now() > deadline) return false;
    await wait(POLL_MS);
  }
  await wait(SETTLE_MS);
  apps.RunGame(gameId, "", -1, 100);
  return true;
}
