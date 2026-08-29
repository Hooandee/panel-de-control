import { describe, expect, it } from "vitest";

import type { CssLoaderPatch, CssLoaderTheme } from "../cssLoaderTypes";
import { obsidianConfigFromTheme } from "./obsidianConfig";

function theme(patches: CssLoaderPatch[]): CssLoaderTheme {
  return {
    id: "Hooandee Obsidian Bloom",
    name: "Hooandee Obsidian Bloom",
    displayName: "Obsidian Bloom",
    version: "v0.2.0",
    author: "Hooandee",
    enabled: true,
    patches,
  };
}

function patch(name: string, value: string): CssLoaderPatch {
  return {
    name,
    defaultValue: value,
    value,
    options: [value],
    type: "dropdown",
    rawType: "dropdown",
  };
}

describe("Obsidian Bloom runtime config", () => {
  it("derives every engine scene from verified CSS Loader patch values", () => {
    expect(obsidianConfigFromTheme(theme([
      patch("Animaciones de parrilla", "Yes"),
      patch("Intensidad de movimiento", "Total"),
      patch("Fondo adaptativo", "Inmersivo"),
      patch("Modo de rendimiento", "No"),
      patch("Escena de biblioteca", "Inmersiva"),
      patch("Escena de parrilla", "Abismo orbital"),
      patch("Transición al detalle", "Portal"),
      patch("Estilo de ajustes", "Cometa"),
    ]))).toEqual({
      gridMotion: true,
      motionIntensity: "full",
      adaptiveBackdrop: "immersive",
      performance: false,
      libraryScene: "immersive",
      gridScene: "abyss",
      detailTransition: "portal",
      settingsScene: "comet",
    });
  });

  it("keeps the previous constellation scene available as a conservative option", () => {
    expect(obsidianConfigFromTheme(theme([
      patch("Animaciones de parrilla", "Yes"),
      patch("Intensidad de movimiento", "Equilibrada"),
      patch("Fondo adaptativo", "Cinemático"),
      patch("Modo de rendimiento", "No"),
      patch("Escena de biblioteca", "Atmosférica"),
      patch("Escena de parrilla", "Constelación"),
      patch("Transición al detalle", "Portal"),
      patch("Estilo de ajustes", "Cometa"),
    ])).gridScene).toBe("constellation");
  });

  it("fails closed when patches are absent or contain unknown values", () => {
    expect(obsidianConfigFromTheme(theme([
      patch("Animaciones de parrilla", "Maybe"),
      patch("Intensidad de movimiento", "Hyper"),
      patch("Fondo adaptativo", "Unknown"),
      patch("Modo de rendimiento", "Unknown"),
      patch("Escena de biblioteca", "Unknown"),
      patch("Escena de parrilla", "Unknown"),
      patch("Transición al detalle", "Unknown"),
      patch("Estilo de ajustes", "Unknown"),
    ]))).toEqual({
      gridMotion: false,
      motionIntensity: "reduced",
      adaptiveBackdrop: "off",
      performance: true,
      libraryScene: "essential",
      gridScene: "direct",
      detailTransition: "none",
      settingsScene: "native",
    });
  });
});
