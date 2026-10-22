import { accessoryEvent } from "../api";

export const PORTRAIT_W = 36;

interface StoreOverview {
  m_setStoreTags?: Iterable<number>;
  minutes_playtime_forever?: number;
}

interface Achievement {
  bAchieved?: boolean;
}

export interface GameInfo {
  appid: string;
  tags: number[];
  playtime_min: number | null;
  achievements: { done: number; total: number } | null;
  portrait?: string;
}

export function gameInfoFrom(appid: string, overview: StoreOverview | null, achievements: Achievement[] | null): GameInfo {
  const tags = overview?.m_setStoreTags ? Array.from(overview.m_setStoreTags).filter((tag) => Number.isInteger(tag)) : [];
  const playtime = overview?.minutes_playtime_forever;
  return {
    appid,
    tags,
    playtime_min: typeof playtime === "number" && playtime >= 0 ? playtime : null,
    achievements: achievements && achievements.length
      ? { done: achievements.filter((a) => a.bAchieved).length, total: achievements.length }
      : null,
  };
}

function overviewOf(liveAppid: number): StoreOverview | null {
  try {
    const store = (window as unknown as { appStore?: { GetAppOverviewByAppID(id: number): StoreOverview | null } }).appStore;
    return store?.GetAppOverviewByAppID(liveAppid) ?? null;
  } catch {
    return null;
  }
}

async function achievementsOf(liveAppid: number): Promise<Achievement[] | null> {
  try {
    const result = await SteamClient.Apps.GetMyAchievementsForApp(String(liveAppid));
    const list = (result as { data?: { rgAchievements?: Achievement[] } } | null)?.data?.rgAchievements;
    return Array.isArray(list) ? list : null;
  } catch {
    return null;
  }
}

let latest: { appid: string; liveAppid: number; portrait?: string } | null = null;

/** Tags, play time and achievement count of the running game, for the pet and the cover scene. */
export async function sendGameInfo(appid: string, liveAppid: number, portrait?: string | null): Promise<boolean> {
  latest = { appid, liveAppid, portrait: portrait ?? undefined };
  const info = gameInfoFrom(appid, overviewOf(liveAppid), await achievementsOf(liveAppid));
  if (portrait) info.portrait = portrait;
  try {
    return await accessoryEvent("game_info", info as unknown as Record<string, unknown>);
  } catch {
    return false;
  }
}

export function refreshGameInfo(): void {
  if (latest) void sendGameInfo(latest.appid, latest.liveAppid, latest.portrait);
}
