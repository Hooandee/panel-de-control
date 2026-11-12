import { listInstalledGames } from "../launch/steamApi";
import { readRunningGame } from "../tdp/runningGame";
import { readCoverBadges, readInGameMode, reportedAppids } from "../upscalers/overlays";

const MAX_GAMES = 12;
const DETAILS_MS = 1500;

/** Facts only Steam knows, read live: what it will launch with and under which licence and Proton. */
export interface SteamGameFacts {
  ownership_flags: number | null;
  owned_by_user: boolean | null;
  free: boolean | null;
  beta: string | null;
  build_id: number | null;
  compat_tool: string | null;
  // Reduced to its technical parts by the backend before anything is kept.
  launch_options: string | null;
}

type Details = {
  eAppOwnershipFlags?: number; strOwnerSteamID?: string; bIsFreeApp?: boolean; strSelectedBeta?: string;
  nBuildID?: number; strCompatToolName?: string; strLaunchOptions?: string;
};

function readDetails(appid: number): Promise<Details | null> {
  return new Promise((resolve) => {
    let done = false;
    let registration: { unregister?: () => void } | undefined;
    const finish = (value: Details | null) => {
      if (done) return;
      done = true;
      try { registration?.unregister?.(); } catch { /* already gone */ }
      resolve(value);
    };
    try {
      registration = (globalThis as any).SteamClient?.Apps?.RegisterForAppDetails?.(appid, (details: Details) => finish(details));
    } catch { finish(null); }
    setTimeout(() => finish(null), DETAILS_MS);
  });
}

export function steamFacts(details: Details, userId: string | null): SteamGameFacts {
  return {
    ownership_flags: typeof details.eAppOwnershipFlags === "number" ? details.eAppOwnershipFlags : null,
    // Only whether the licence is the signed-in user's: the owner's id itself never leaves the device.
    owned_by_user: details.strOwnerSteamID && userId ? details.strOwnerSteamID === userId : null,
    free: typeof details.bIsFreeApp === "boolean" ? details.bIsFreeApp : null,
    beta: typeof details.strSelectedBeta === "string" ? details.strSelectedBeta.slice(0, 64) : null,
    build_id: typeof details.nBuildID === "number" ? details.nBuildID : null,
    compat_tool: typeof details.strCompatToolName === "string" ? details.strCompatToolName.slice(0, 80) : null,
    launch_options: typeof details.strLaunchOptions === "string" ? details.strLaunchOptions.slice(0, 4096) : null,
  };
}

export async function upscalersReportContext() {
  const collected_at = new Date().toISOString();
  const badges = { covers: readCoverBadges(), in_game: readInGameMode() };
  let running: { stable_appid: string; live_appid: string; name: string; is_non_steam: boolean | null } | null = null;
  try {
    const current = readRunningGame();
    if (current) {
      const entry = listInstalledGames().find((game) => game.liveAppid === current.liveAppid);
      running = {
        stable_appid: current.appid.slice(0, 256),
        live_appid: String(current.liveAppid),
        name: current.name.slice(0, 256),
        is_non_steam: entry?.isNonSteam ?? null,
      };
    }
  } catch {
    return { collected_at, status: "unavailable", badges, running: null, games: {} };
  }
  const games: Record<string, SteamGameFacts> = {};
  try {
    const userId = (globalThis as any).App?.m_CurrentUser?.strSteamID ?? null;
    const appids = [...new Set([...(running ? [running.live_appid] : []), ...reportedAppids()])].slice(0, MAX_GAMES);
    const details = await Promise.all(appids.map((appid) => readDetails(Number(appid))));
    appids.forEach((appid, index) => {
      if (details[index]) games[appid] = steamFacts(details[index]!, typeof userId === "string" ? userId : null);
    });
  } catch { /* the report still goes out with what the backend reads itself */ }
  return { collected_at, status: "available", badges, running, games };
}
