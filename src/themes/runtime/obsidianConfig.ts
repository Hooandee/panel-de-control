import type { CssLoaderTheme } from "../cssLoaderTypes";
import type { ConstellationScene } from "./constellationFocus";

export type MotionIntensity = "reduced" | "balanced" | "full";
export type AdaptiveBackdrop = "off" | "subtle" | "cinematic" | "immersive";
export type LibraryScene = "essential" | "atmospheric" | "immersive";
export type DetailTransition = "none" | "fade" | "portal";
export type SettingsScene = "native" | "glass" | "comet";
export type GridScene = ConstellationScene | "abyss";

export interface ObsidianBloomConfig {
  gridMotion: boolean;
  motionIntensity: MotionIntensity;
  adaptiveBackdrop: AdaptiveBackdrop;
  performance: boolean;
  libraryScene: LibraryScene;
  gridScene: GridScene;
  detailTransition: DetailTransition;
  settingsScene: SettingsScene;
}

function patchValue(theme: CssLoaderTheme, name: string): string | undefined {
  return theme.patches.find((patch) => patch.name === name)?.value;
}

export function obsidianConfigFromTheme(theme: CssLoaderTheme): ObsidianBloomConfig {
  const motion = patchValue(theme, "Intensidad de movimiento");
  const backdrop = patchValue(theme, "Fondo adaptativo");
  const libraryScene = patchValue(theme, "Escena de biblioteca");
  const gridScene = patchValue(theme, "Escena de parrilla");
  const detailTransition = patchValue(theme, "Transición al detalle");
  const settingsScene = patchValue(theme, "Estilo de ajustes");

  return {
    gridMotion: patchValue(theme, "Animaciones de parrilla") === "Yes",
    motionIntensity: motion === "Total" ? "full" : motion === "Equilibrada" ? "balanced" : "reduced",
    adaptiveBackdrop: backdrop === "Inmersivo"
      ? "immersive"
      : backdrop === "Cinemático"
        ? "cinematic"
        : backdrop === "Sutil"
          ? "subtle"
          : "off",
    performance: patchValue(theme, "Modo de rendimiento") !== "No",
    libraryScene: libraryScene === "Inmersiva"
      ? "immersive"
      : libraryScene === "Atmosférica"
        ? "atmospheric"
        : "essential",
    gridScene: gridScene === "Abismo orbital"
      ? "abyss"
      : gridScene === "Constelación"
      ? "constellation"
      : gridScene === "Órbita"
        ? "orbit"
        : "direct",
    detailTransition: detailTransition === "Portal"
      ? "portal"
      : detailTransition === "Fundido"
        ? "fade"
        : "none",
    settingsScene: settingsScene === "Cometa"
      ? "comet"
      : settingsScene === "Cristal"
        ? "glass"
        : "native",
  };
}
