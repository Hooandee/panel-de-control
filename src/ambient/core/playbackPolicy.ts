export type Source = "music" | "radio";

export interface PlaybackPlan {
  playing: boolean;
  volumeScale: number;
}

/** In-game media level: 0 pauses, anything else scales the listener's volume. */
export function planForGameState(inGame: boolean, mediaLevel: number): PlaybackPlan {
  if (!inGame) return { playing: true, volumeScale: 1 };
  const level = Math.max(0, Math.min(100, mediaLevel));
  return level === 0 ? { playing: false, volumeScale: 1 } : { playing: true, volumeScale: level / 100 };
}

export const RADIO_RETRY_DELAYS_MS = [2000, 5000, 10000] as const;

export function nextRetryDelay(attempt: number): number | null {
  return attempt < RADIO_RETRY_DELAYS_MS.length ? RADIO_RETRY_DELAYS_MS[attempt] : null;
}

/**
 * The game's own volume while playing: the chosen mix only while Ambiente's media sounds. Once it
 * stops, full volume is put back only if Panel lowered it; otherwise the game's streams are left alone.
 */
export function gameVolumeTarget(inGame: boolean, mediaPlaying: boolean, gameLevel: number, lowered: boolean): number | null {
  if (!inGame) return null;
  const level = Math.max(0, Math.min(100, Math.round(gameLevel)));
  if (mediaPlaying && level < 100) return level;
  return lowered ? 100 : null;
}
