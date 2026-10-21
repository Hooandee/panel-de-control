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

    expect(gallery).toBeTruthy();
    expect(atlas).toBeTruthy();
    expect(eclipse).toBeTruthy();
    expect(new Set([gallery, atlas, eclipse]).size).toBe(3);
  });

  it("gives no cover to an unknown theme or one whose identity does not match", () => {
    expect(themeCoverFor(release("someone-else", "Hooandee Luminous Atlas"))).toBeUndefined();
    expect(themeCoverFor(release("hooandee-luminous-atlas", "Other Name"))).toBeUndefined();
  });
});

describe("themeDescriptionFor", () => {
  it("describes Hooandee themes in German, Brazilian Portuguese and French, which the catalog cannot carry", () => {
    for (const [catalogId, cssLoaderName] of [
      ["hooandee-gallery", "Hooandee Gallery"],
      ["hooandee-luminous-atlas", "Hooandee Luminous Atlas"],
      ["hooandee-eclipse", "Hooandee Eclipse"],
    ]) {
      const de = themeDescriptionFor(release(catalogId, cssLoaderName), "de");
      const pt = themeDescriptionFor(release(catalogId, cssLoaderName), "pt-BR");
      expect(de).not.toBe("Published description.");
      expect(pt).not.toBe("Published description.");
      const fr = themeDescriptionFor(release(catalogId, cssLoaderName), "fr");
      expect(de).not.toBe(pt);
      expect(fr).not.toBe("Published description.");
      expect(fr).not.toBe(de);
    }
  });

  it("keeps the published text for the catalog's own languages and for other themes", () => {
    const eclipse = release("hooandee-eclipse", "Hooandee Eclipse");
    expect(themeDescriptionFor(eclipse, "es")).toBe("Descripción publicada.");
    expect(themeDescriptionFor(eclipse, "it")).toBe("Descrizione pubblicata.");
    expect(themeDescriptionFor(release("someone-else", "Someone"), "de")).toBe("Published description.");
    expect(themeDescriptionFor(release("hooandee-eclipse", "Other Name"), "pt-BR")).toBe("Published description.");
  });
});

describe("themeTaglineFor", () => {
  const hooandee = [
    ["hooandee-duo", "Hooandee Duo"],
    ["hooandee-gallery", "Hooandee Gallery"],
    ["hooandee-luminous-atlas", "Hooandee Luminous Atlas"],
    ["hooandee-eclipse", "Hooandee Eclipse"],
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
