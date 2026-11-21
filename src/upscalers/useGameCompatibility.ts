import { useEffect, useRef, useState } from "react";
import { getUpscalersCompat, type GameCompat } from "../api";
import type { GameEntry } from "../launch/steamApi";
import { steamLibraryFolders } from "./steamLibraries";

type Compatibility = Record<string, GameCompat>;
const empty: Compatibility = {};

export function useGameCompatibility(games: GameEntry[], enabled: boolean) {
  const requests = useRef(new Map<string, Promise<Compatibility>>());
  const lastFolders = useRef("");
  const [result, setResult] = useState<{ ids: Set<string>; compat: Compatibility } | null>(null);
  const key = enabled ? games.map((game) => String(game.liveAppid)).sort().join(",") : "";

  useEffect(() => {
    const ids = new Set(key ? key.split(",") : []);
    const cache = requests.current;
    const folders = steamLibraryFolders();
    const folderKey = JSON.stringify(folders);
    if (lastFolders.current !== folderKey) cache.clear();
    lastFolders.current = folderKey;
    for (const id of cache.keys()) if (!ids.has(id)) cache.delete(id);
    if (!ids.size) return;

    let active = true;
    const missing = [...ids].filter((id) => !cache.has(id));
    // The backend accepts at most 400 AppIDs per request.
    for (let i = 0; i < missing.length; i += 400) {
      const batch = missing.slice(i, i + 400);
      const request = getUpscalersCompat(batch, folders).catch(() => empty);
      for (const id of batch) cache.set(id, request);
    }
    Promise.all(new Set(cache.values())).then((parts) => {
      if (!active) return;
      const compat = Object.assign({}, ...parts);
      for (const id of ids) if (!compat[id]) cache.delete(id);
      setResult({ ids, compat });
    });
    return () => { active = false; };
  }, [key]);

  const compat = result?.compat ?? empty;
  const checked = result?.ids;
  const status = !enabled || games.some((game) => !checked?.has(String(game.liveAppid))) ? "pending"
    : games.some((game) => !compat[String(game.liveAppid)]) ? "partial" : "ready";
  return { compat, checked, status } as const;
}
