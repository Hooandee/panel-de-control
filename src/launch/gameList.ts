import { AMBIGUOUS, detectSelections } from "./catalog";
import { parse } from "./compose";

export function activeCountFromRaw(raw: string | null): number | null {
  if (raw === null) return null;
  const parsed = parse(raw);
  if (parsed.malformed) return null;
  return Object.values(detectSelections(parsed)).filter(
    (value) => value !== false && value !== AMBIGUOUS,
  ).length;
}

interface UnknownCountGame {
  liveAppid: number;
  activeCount: number | null;
}

export async function hydrateUnknownCounts<T extends UnknownCountGame>(
  games: readonly T[],
  read: (appid: number) => Promise<{ launch: string } | null>,
  update: (appid: number, count: number | null) => void,
  concurrency = 6,
): Promise<void> {
  const pending = games.filter((game) => game.activeCount === null);
  let cursor = 0;
  const worker = async () => {
    while (cursor < pending.length) {
      const game = pending[cursor++];
      let count: number | null = null;
      try {
        const details = await read(game.liveAppid);
        count = activeCountFromRaw(details?.launch ?? null);
      } catch {
        count = null;
      }
      update(game.liveAppid, count);
    }
  };
  await Promise.all(Array.from({ length: Math.min(Math.max(1, concurrency), pending.length) }, worker));
}
