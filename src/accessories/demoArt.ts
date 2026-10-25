import { readRunningGame } from "../tdp/runningGame";
import { panelPixels, PORTRAIT_FILES } from "./gameArt";
import { achievementsOf, gameInfoFrom, overviewOf, PORTRAIT_W } from "./gameInfo";

interface LibraryApp {
  appid: number;
  app_type?: number;
  display_name?: string;
  minutes_playtime_forever?: number;
}

let cached: Promise<Record<string, unknown> | null> | null = null;

function candidates(): LibraryApp[] {
  const running = readRunningGame();
  const store = (window as unknown as { appStore?: { allApps?: Iterable<LibraryApp> } }).appStore;
  const games = [...(store?.allApps ?? [])].filter((app) => app.app_type === 1)
    .sort((a, b) => (b.minutes_playtime_forever ?? 0) - (a.minutes_playtime_forever ?? 0));
  const first = running ? games.find((app) => app.appid === running.liveAppid) : undefined;
  return [...(first ? [first] : []), ...games].slice(0, 6);
}

/** Art and numbers of the running game, or the most played one, for the cover shots of the demo. */
export function demoArt(): Promise<Record<string, unknown> | null> {
  cached ??= (async () => {
    for (const app of candidates()) {
      const rgb = await panelPixels(app.appid);
      if (!rgb) continue;
      const portrait = await panelPixels(app.appid, PORTRAIT_FILES, PORTRAIT_W);
      const info = gameInfoFrom(String(app.appid), overviewOf(app.appid), await achievementsOf(app.appid));
      return { appid: String(app.appid), name: app.display_name ?? "", rgb, portrait, playtime_min: info.playtime_min,
        achievements: info.achievements };
    }
    return null;
  })().catch(() => null);
  return cached;
}
