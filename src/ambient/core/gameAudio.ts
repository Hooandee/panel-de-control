import type { GameAudioSource } from "./types";

export const GAME_AUDIO_SOURCES: readonly GameAudioSource[] = ["auto", "trailerFirst", "musicOnly", "trailerOnly"];

export type GameAudioPick = "theme" | "trailer" | null;

/**
 * What a selected game sounds with. "auto" is the original behaviour: its soundtrack, and the trailer's own
 * audio only when no soundtrack was found.
 */
export function pickGameAudio(source: GameAudioSource, available: { theme: boolean; trailer: boolean }): GameAudioPick {
  const theme = available.theme ? "theme" : null;
  const trailer = available.trailer ? "trailer" : null;
  switch (source) {
    case "trailerFirst": return trailer ?? theme;
    case "musicOnly": return theme;
    case "trailerOnly": return trailer;
    default: return theme ?? trailer;
  }
}
