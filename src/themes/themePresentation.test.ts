import { describe, expect, it } from "vitest";

import { themeCoverFor, themeDescriptionFor } from "./themePresentation";
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
  it("describes Hooandee themes in German and Brazilian Portuguese, which the catalog cannot carry", () => {
    for (const [catalogId, cssLoaderName] of [
      ["hooandee-gallery", "Hooandee Gallery"],
      ["hooandee-luminous-atlas", "Hooandee Luminous Atlas"],
      ["hooandee-eclipse", "Hooandee Eclipse"],
    ]) {
      const de = themeDescriptionFor(release(catalogId, cssLoaderName), "de");
      const pt = themeDescriptionFor(release(catalogId, cssLoaderName), "pt-BR");
      expect(de).not.toBe("Published description.");
      expect(pt).not.toBe("Published description.");
      expect(de).not.toBe(pt);
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
