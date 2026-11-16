import { useEffect, useState } from "react";

import { listHudGames } from "../api";

/** Stable keys of the games that apply their own HUD (empty until the backend answers). */
export function useHudGames(): ReadonlySet<string> {
  const [games, setGames] = useState<ReadonlySet<string>>(() => new Set());
  useEffect(() => {
    let alive = true;
    listHudGames()
      .then((keys) => {
        if (alive && Array.isArray(keys)) setGames(new Set(keys));
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);
  return games;
}
