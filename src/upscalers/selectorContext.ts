import type { GameEntry, readUpscalersSelection, SelectorSteamMetadata } from "../launch/steamApi";
import { recordUiEvent } from "../system/uiEvents";

type SelectorSample = SelectorSteamMetadata & { row: "visible" | "unavailable" };

interface SelectorSnapshot {
  observed_at: number;
  complete: boolean | null;
  compatibility: "ready" | "pending" | "partial";
  recovered: number;
  steam_rows: number;
  shortcut_rows: number;
  filtered: number;
  unavailable?: Record<string, number>;
  no_metadata: number;
  not_game: number;
  unreadable: number;
  manifest_rejected?: Record<string, number>;
  samples: SelectorSample[];
}

type Selection = ReturnType<typeof readUpscalersSelection>;
let omitted: Selection["omitted"] | undefined;
let snapshot: SelectorSnapshot | null = null;
let status: "unopened" | "failed" | "observed" = "unopened";

export function readSelectorContext(reportAppids: string[] = []) {
  const omissions = reportAppids.flatMap((id) => {
    const appid = Number(id);
    const reason = omitted?.get(appid);
    return reason ? [{ appid, reason }] : [];
  });
  return { selector: snapshot && omissions.length ? { ...snapshot, omissions } : snapshot, selector_status: status };
}

export function publishSelectorFailure() {
  status = "failed";
  snapshot = null;
  omitted = undefined;
  recordUiEvent("upscalers", "selector", { status }, false);
}

export function publishSelectorContext(selection: Selection, listed: GameEntry[], complete: boolean | null,
  compatibility: SelectorSnapshot["compatibility"], filtered: number, rejected?: Record<string, number>,
  unavailable?: Record<string, number>) {
  const visible = new Set(listed.map((game) => game.liveAppid));
  const disagrees = (app: SelectorSteamMetadata) => !app.collection || app.local !== "true";
  const priority = (app: SelectorSteamMetadata) => Number(disagrees(app) || !visible.has(app.appid));
  const samples: SelectorSample[] = [...selection.steam]
    .sort((a, b) => priority(b) - priority(a))
    .slice(0, 12)
    .map((app) => ({ ...app, row: visible.has(app.appid) ? "visible" : "unavailable" }));
  const shortcut_rows = listed.filter((game) => game.isNonSteam).length;
  const counts = {
    observed_at: Math.floor(Date.now() / 1000), complete, compatibility,
    recovered: selection.steam.filter((app) => app.manifest && disagrees(app)).length,
    steam_rows: listed.length - shortcut_rows, shortcut_rows, filtered,
    no_metadata: selection.no_metadata, not_game: selection.not_game, unreadable: selection.unreadable,
    ...(rejected ? { manifest_rejected: rejected } : {}),
    ...(unavailable && Object.keys(unavailable).length ? { unavailable } : {}),
  };
  status = "observed";
  omitted = selection.omitted;
  snapshot = { ...counts, samples };
  recordUiEvent("upscalers", "selector", { status, ...counts });
}
