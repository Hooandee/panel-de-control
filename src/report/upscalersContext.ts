import { listInstalledGames } from "../launch/steamApi";
import { readRunningGame } from "../tdp/runningGame";

export function upscalersReportContext() {
  const collected_at = new Date().toISOString();
  try {
    const running = readRunningGame();
    if (!running) return { collected_at, status: "available", running: null };
    const entry = listInstalledGames().find((game) => game.liveAppid === running.liveAppid);
    return {
      collected_at,
      status: "available",
      running: {
        stable_appid: running.appid.slice(0, 256),
        live_appid: String(running.liveAppid),
        name: running.name.slice(0, 256),
        is_non_steam: entry?.isNonSteam ?? null,
      },
    };
  } catch {
    return { collected_at, status: "unavailable", running: null };
  }
}
