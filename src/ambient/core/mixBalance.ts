export interface MixLevels { game: number; media: number }

const level = (value: number) => Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : 0;

export function mixBalance(game: number, media: number): number {
  const g = level(game), m = level(media), peak = Math.max(g, m);
  return peak ? Math.round((m - g) / peak * 100) : 0;
}

// Preserve the existing ceiling: changing balance must not raise both saved volumes.
export function levelsForBalance(position: number, game: number, media: number): MixLevels {
  const balance = Number.isFinite(position) ? Math.max(-100, Math.min(100, position)) : 0;
  const peak = Math.max(level(game), level(media));
  return {
    game: Math.round(peak * (balance > 0 ? 1 - balance / 100 : 1)),
    media: Math.round(peak * (balance < 0 ? 1 + balance / 100 : 1)),
  };
}
