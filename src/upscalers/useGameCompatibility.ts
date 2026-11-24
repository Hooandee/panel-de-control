import { useEffect, useRef, useState } from "react";
import { getUpscalersCompat, type GameCompat } from "../api";
import type { GameEntry } from "../launch/steamApi";
import { steamLibraryFolders } from "./steamLibraries";

type Compatibility = Record<string, GameCompat>;
const empty: Compatibility = {};

export function useGameCompatibility(games: GameEntry[], enabled: boolean) {
  const requests = useRef(new Map<string, Promise<GameCompat | undefined>>());
  const lastFolders = useRef("");
  const shortcuts = useRef(new Set<string>());
  const [result, setResult] = useState<{ ids: Set<string>; compat: Compatibility } | null>(null);
  const key = enabled ? games.map((game) => String(game.liveAppid)).sort().join(",") : "";
  shortcuts.current = new Set(games.filter((game) => game.isNonSteam).map((game) => String(game.liveAppid)));

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
    // Shortcuts ask first and alone: Steam libraries can take long to read, and a shortcut waits only for its own answer.
    const missing = [...ids].filter((id) => !cache.has(id));
    const batches: string[][] = [];
    for (const group of [missing.filter((id) => shortcuts.current.has(id)), missing.filter((id) => !shortcuts.current.has(id))]) {
      // The backend accepts at most 400 AppIDs per request.
      for (let i = 0; i < group.length; i += 400) batches.push(group.slice(i, i + 400));
    }
    for (const batch of batches) {
      const request = getUpscalersCompat(batch, folders).catch(() => empty);
      for (const id of batch) cache.set(id, request.then((rows) => rows[id]));
    }

    const answered = new Map<string, GameCompat | undefined>();
    let queued = false;
    const publish = () => {
      queued = false;
      if (!active) return;
      const compat: Compatibility = {};
      for (const [id, row] of answered) if (row) compat[id] = row;
      setResult({ ids: new Set(answered.keys()), compat });
    };
    for (const [id, request] of cache) {
      void request.then((row) => {
        if (!active) return;
        answered.set(id, row);
        if (!row) cache.delete(id);
        if (!queued) {
          queued = true;
          queueMicrotask(publish);
        }
      });
    }
    return () => { active = false; };
  }, [key]);

  const compat = result?.compat ?? empty;
  const checked = result?.ids;
  const status = !enabled || games.some((game) => !checked?.has(String(game.liveAppid))) ? "pending"
    : games.some((game) => !compat[String(game.liveAppid)]) ? "partial" : "ready";
  return { compat, checked, status } as const;
}
