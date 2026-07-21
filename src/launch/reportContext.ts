import { getProtonCaps } from "../api";
import { readRunningGame } from "../tdp/runningGame";
import { listInstalledGames, readAppDetails } from "./steamApi";
import { parse } from "./compose";
import { detectSelections } from "./catalog";

/** Best-effort launch diagnostics for a bug report — the frontend-only signals the
 *  backend can't read: the running game's actual launch-options string, whether our
 *  parser rejects it, and its Proton compat tool + supported var count. (Tools,
 *  custom-var count and hidden count come from the backend `launch` state.) Never
 *  throws; any missing piece is simply absent. The launch string (which may hold
 *  paths) is redacted server-side with the rest of the bundle. */
export async function launchReportContext(): Promise<Record<string, unknown>> {
  const ctx: Record<string, unknown> = {};
  try {
    const running = readRunningGame();
    if (!running) {
      ctx.runningGame = null;
      return ctx;
    }
    const game = listInstalledGames().find((g) => g.stableKey === running.appid);
    if (!game) {
      ctx.runningGame = { note: "running game not in list" };
      return ctx;
    }
    const g: Record<string, unknown> = { name: game.name, isNonSteam: game.isNonSteam, hasCover: game.coverUrls.length > 0 };
    const details = await readAppDetails(game.liveAppid);
    g.detailsRead = details !== null;
    if (details) {
      const parsed = parse(details.launch);
      g.launchOptions = details.launch;
      g.malformed = parsed.malformed;
      g.activePills = Object.keys(detectSelections(parsed));
      g.compatTool = details.compatName;
      g.compatDisplay = details.compatDisplay;
      try {
        const caps = await getProtonCaps(details.compatName);
        g.protonFound = caps.found;
        g.protonVarCount = caps.envs.length;
      } catch {
        /* ignore */
      }
    }
    ctx.runningGame = g;
  } catch {
    /* ignore */
  }
  return ctx;
}
