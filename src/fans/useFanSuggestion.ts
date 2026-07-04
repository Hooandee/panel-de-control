import { useCallback, useEffect, useState } from "react";
import { getFanSuggestion, FanSuggestion } from "../api";

/**
 * Fetches the fan-curve suggestion for the given game (per-game only). Refetches
 * when the appid changes. Returns null until the first RPC lands. The appid is
 * passed in (not read via a second useRunningGame) so it stays in lock-step with
 * the curve control's scope/game.
 */
export function useFanSuggestion(appid: string | null) {
  const [suggestion, setSuggestion] = useState<FanSuggestion | null>(null);

  const refresh = useCallback(() => {
    getFanSuggestion(appid).then(setSuggestion).catch(() => {});
  }, [appid]);

  useEffect(() => {
    // Drop the previous game's suggestion immediately on appid change — never show
    // (or let the user apply) one game's learned curve labeled as another's while
    // the new RPC is in flight. The prominent, open-by-default card makes this
    // window actionable, so blanking here is a correctness guard.
    setSuggestion(null);
    refresh();
  }, [appid, refresh]);

  return { suggestion, refresh };
}
