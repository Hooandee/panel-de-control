import type { GameArtMode } from "./types";

export type NativeArt = "show" | "blend" | "hide";

export interface BackgroundChoice {
  mediaRef: string | null;
  nativeArt: NativeArt;
}

export const BLEND_GAME_ART_OPACITY = 0.45;

/** Per-game background wins, then the selected mode decides how Steam's game art shows over it. */
export function chooseBackground(
  mode: GameArtMode,
  rotationRef: string | null,
  selectedAppId: string | null,
  perGame: Record<string, string>,
): BackgroundChoice {
  const perGameRef = selectedAppId ? perGame[selectedAppId] : undefined;
  if (perGameRef) return { mediaRef: perGameRef, nativeArt: "hide" };
  if (mode === "game" || rotationRef === null) return { mediaRef: null, nativeArt: "show" };
  return { mediaRef: rotationRef, nativeArt: mode === "blend" ? "blend" : "hide" };
}
