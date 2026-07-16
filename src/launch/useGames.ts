import { useCallback, useEffect, useState } from "react";

import { parse } from "./compose";
import { detectSelections } from "./catalog";
import { GameEntry, listInstalledGames, readLaunchOptionsSync } from "./steamApi";

export interface GameListItem extends GameEntry {
  /** How many of our pills are already active in this game's string (0 = none / uncached). */
  activeCount: number;
}

/** Installed games (Steam + non-Steam) for the section, with a per-row active-pill count. */
export function useGames(): { games: GameListItem[] | null; reload: () => void } {
  const [games, setGames] = useState<GameListItem[] | null>(null);

  const reload = useCallback(() => {
    const list = listInstalledGames().map((g) => {
      const raw = readLaunchOptionsSync(g.liveAppid);
      const activeCount = raw == null ? 0 : Object.keys(detectSelections(parse(raw))).length;
      return { ...g, activeCount };
    });
    setGames(list);
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  return { games, reload };
}
