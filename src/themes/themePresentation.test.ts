import { describe, expect, it } from "vitest";

import { SUPPORTED_LANGUAGES } from "../i18n/languages";
import { themeCoverFor, themeDescriptionFor, themeTaglineFor } from "./themePresentation";
import type { PublishedThemeRelease } from "./remotePublication";

function release(catalogId: string, cssLoaderName: string): PublishedThemeRelease {
  return {
    catalogId,
    cssLoaderName,
    description: { es: "Descripción publicada.", en: "Published description.", it: "Descrizione pubblicata." },
  } as PublishedThemeRelease;
}

describe("themeCoverFor", () => {
  it("gives each Hooandee theme its own cover", () => {
    const gallery = themeCoverFor(release("hooandee-gallery", "Hooandee Gallery"));
    const atlas = themeCoverFor(release("hooandee-luminous-atlas", "Hooandee Luminous Atlas"));
    const eclipse = themeCoverFor(release("hooandee-eclipse", "Hooandee Eclipse"));
    const vida = themeCoverFor(release("hooandee-vida", "Hooandee Vida"));

    expect(gallery).toBeTruthy();
    expect(atlas).toBeTruthy();
    expect(eclipse).toBeTruthy();
    expect(vida).toBeTruthy();
    expect(new Set([gallery, atlas, eclipse, vida]).size).toBe(4);
  });

  it("gives no cover to an unknown theme or one whose identity does not match", () => {
    expect(themeCoverFor(release("someone-else", "Hooandee Luminous Atlas"))).toBeUndefined();
    expect(themeCoverFor(release("hooandee-luminous-atlas", "Other Name"))).toBeUndefined();
  });
});

describe("themeDescriptionFor", () => {
  const hooandee = [
    ["hooandee-vida", "Hooandee Vida"],
    ["hooandee-duo", "Hooandee Duo"],
    ["hooandee-gallery", "Hooandee Gallery"],
    ["hooandee-luminous-atlas", "Hooandee Luminous Atlas"],
    ["hooandee-eclipse", "Hooandee Eclipse"],
  ] as const;

  it("describes every Hooandee theme in every language from one place", () => {
    for (const [catalogId, cssLoaderName] of hooandee) {
      const lines = SUPPORTED_LANGUAGES.map((lang) => themeDescriptionFor(release(catalogId, cssLoaderName), lang));
      for (const line of lines) expect(line).not.toMatch(/published|publicada|pubblicata/i);
      expect(new Set(lines).size).toBe(SUPPORTED_LANGUAGES.length);
    }
  });

  it("keeps the published text for themes that are not Hooandee's or whose identity does not match", () => {
    expect(themeDescriptionFor(release("someone-else", "Someone"), "es")).toBe("Descripción publicada.");
    expect(themeDescriptionFor(release("someone-else", "Someone"), "de")).toBe("Published description.");
    expect(themeDescriptionFor(release("hooandee-eclipse", "Other Name"), "it")).toBe("Descrizione pubblicata.");
  });
});

describe("themeTaglineFor", () => {
  const hooandee = [
    ["hooandee-duo", "Hooandee Duo"],
    ["hooandee-gallery", "Hooandee Gallery"],
    ["hooandee-luminous-atlas", "Hooandee Luminous Atlas"],
    ["hooandee-eclipse", "Hooandee Eclipse"],
    ["hooandee-vida", "Hooandee Vida"],
  ] as const;

  it("gives every Hooandee theme a short line in every language", () => {
    for (const [catalogId, cssLoaderName] of hooandee) {
      for (const lang of SUPPORTED_LANGUAGES) {
        const line = themeTaglineFor(release(catalogId, cssLoaderName), lang);
        expect(line).not.toMatch(/published|publicada|pubblicata/i);
        expect(line.length).toBeLessThanOrEqual(48);
      }
    }
  });

  it("falls back to the published description for other themes", () => {
    expect(themeTaglineFor(release("someone-else", "Someone"), "es")).toBe("Descripción publicada.");
    expect(themeTaglineFor(release("hooandee-duo", "Other Name"), "en")).toBe("Published description.");
  });
});
