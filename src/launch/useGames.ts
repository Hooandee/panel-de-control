import { useCallback, useEffect, useRef, useState } from "react";

import { activeCountFromRaw, hydrateUnknownCounts } from "./gameList";
import { GameEntry, listInstalledGames, readAppDetails, readLaunchOptionsSync } from "./steamApi";

export interface GameListItem extends GameEntry {
  /** How many of our pills are active; null until Steam supplies uncached details. */
  activeCount: number | null;
}

/** Installed games (Steam + non-Steam) for the section, with a per-row active-pill count. */
export function useGames(): { games: GameListItem[] | null; reload: () => void } {
  const [games, setGames] = useState<GameListItem[] | null>(null);
  const generation = useRef(0);

  const reload = useCallback(() => {
    const current = ++generation.current;
    const list = listInstalledGames().map((g) => {
      const raw = readLaunchOptionsSync(g.liveAppid);
      const activeCount = activeCountFromRaw(raw);
      return { ...g, activeCount };
    });
    setGames(list);
    void hydrateUnknownCounts(list, readAppDetails, (appid, activeCount) => {
      if (generation.current !== current) return;
      setGames((previous) =>
        previous?.map((game) => (game.liveAppid === appid ? { ...game, activeCount } : game)) ?? null,
      );
    });
  }, []);

  useEffect(() => {
    reload();
    return () => {
      generation.current += 1;
    };
  }, [reload]);

  return { games, reload };
}
