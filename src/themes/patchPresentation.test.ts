import { describe, expect, it } from "vitest";

import { presentThemePatchText } from "./patchPresentation";

describe("presentThemePatchText", () => {
  it("translates Obsidian's Spanish CSS Loader contract without changing its raw value", () => {
    expect(presentThemePatchText("Escena de parrilla", "en")).toBe("Grid scene");
    expect(presentThemePatchText("Abismo orbital", "en")).toBe("Orbital Abyss");
    expect(presentThemePatchText("Cinemático", "en")).toBe("Cinematic");
    expect(presentThemePatchText("Yes", "es")).toBe("Sí");
  });

  it("presents every Gallery control label in English", () => {
    const labels = {
      "Color de acento": "Accent color",
      Apariencia: "Appearance",
      "Posición del nombre": "Name position",
      "Mostrar nombre del juego": "Show game title",
      "Mostrar tiempo jugado": "Show playtime",
      "Vista inicial de Detalles": "Initial Details view",
      "Profundidad del carrusel": "Carousel depth",
      "Tamaño de galería": "Gallery size",
      "Primera tarjeta": "First card",
      "Panel de cristal de Inicio": "Home glass panel",
      "Difuminado de parrilla": "Grid blur",
      "Difuminado de detalles": "Details blur",
      "Modo de rendimiento": "Performance mode",
      "Contenido del header": "Header content",
      "Indicadores del header": "Header indicators",
      "Estilo de batería": "Battery style",
      "Contenido del footer": "Footer content",
      "Estilo de iconos del footer": "Footer icon style",
    };

    for (const [raw, translated] of Object.entries(labels)) {
      expect(presentThemePatchText(raw, "en")).toBe(translated);
    }
  });

  it("presents Gallery option values in English while preserving their CSS Loader values", () => {
    const values = {
      Glaciar: "Glacier", Salvia: "Sage", Carmesí: "Crimson", Rosa: "Rose",
      Oscuro: "Dark", Claro: "Light", Arriba: "Top", Abajo: "Bottom",
      Completa: "Full", Pequeño: "Small", Predeterminado: "Default", Grande: "Large",
      "Hero horizontal": "Horizontal hero", "Portada uniforme": "Uniform cover",
      Desactivado: "Off", Suave: "Soft", Medio: "Medium", Alto: "High",
      Completo: "Full", "Solo indicadores": "Indicators only", Oculto: "Hidden",
      "Batería y hora": "Battery and time", "Solo batería": "Battery only",
      "Solo hora": "Time only", Ninguno: "None",
    };

    for (const [raw, translated] of Object.entries(values)) {
      expect(presentThemePatchText(raw, "en")).toBe(translated);
    }
  });

  it("presents Gallery labels and values in Italian", () => {
    expect(presentThemePatchText("Color de acento", "it")).toBe("Colore accento");
    expect(presentThemePatchText("Vista inicial de Detalles", "it")).toBe("Vista iniziale dei dettagli");
    expect(presentThemePatchText("Modo de rendimiento", "it")).toBe("Modalità prestazioni");
    expect(presentThemePatchText("Oscuro", "it")).toBe("Scuro");
    expect(presentThemePatchText("Batería y hora", "it")).toBe("Batteria e ora");
    expect(presentThemePatchText("Yes", "it")).toBe("Sì");
  });

  it("preserves unknown values from current or future CSS Loader themes", () => {
    expect(presentThemePatchText("Future nebula", "en")).toBe("Future nebula");
    expect(presentThemePatchText("Future nebula", "es")).toBe("Future nebula");
  });
});
