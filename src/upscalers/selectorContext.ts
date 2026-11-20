import type { SelectorSteamMetadata } from "../launch/steamApi";
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
  no_metadata: number;
  not_game: number;
  unreadable: number;
  samples: SelectorSample[];
}

let snapshot: SelectorSnapshot | null = null;
let status: "unopened" | "failed" | "observed" = "unopened";

export function readSelectorContext() {
  return { selector: snapshot, selector_status: status };
}

export function publishSelectorContext(next: SelectorSnapshot | null) {
  status = next ? "observed" : "failed";
  snapshot = next;
  if (!next) {
    recordUiEvent("upscalers", "selector", { status }, false);
    return;
  }
  const { samples: _samples, ...counts } = next;
  recordUiEvent("upscalers", "selector", { status, ...counts });
}
