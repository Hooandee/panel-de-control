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
    refresh();
  }, [refresh]);

  return { suggestion, refresh };
}
