import { describe, expect, it } from "vitest";

import { requiredCssLoaderBackendVersion } from "./themesClient";
import type { ThemeCatalog } from "./types";

function entry(
  id: string,
  availability: "available" | "coming-soon",
  minimumCssLoaderBackendVersion: number,
): ThemeCatalog["themes"][number] {
  return {
    id,
    cssLoaderName: id,
    nameKey: `${id}.name`,
    descriptionKey: `${id}.description`,
    availability,
    author: "Hooandee",
    cssLoaderManifestVersion: 9,
    minimumCssLoaderBackendVersion,
    tags: [],
    installSources: [],
  };
}

describe("requiredCssLoaderBackendVersion", () => {
  it("ignores requirements declared by coming-soon catalog entries", () => {
    const catalog: ThemeCatalog = {
      schemaVersion: 1,
      themes: [
        entry("available-theme", "available", 9),
        entry("future-theme", "coming-soon", 999),
      ],
    };

    expect(requiredCssLoaderBackendVersion(catalog)).toBe(9);
  });
});
