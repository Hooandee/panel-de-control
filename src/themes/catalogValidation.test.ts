import { describe, expect, it } from "vitest";

import { LOCAL_THEME_CATALOG } from "./catalog";
import { validateThemeCatalog } from "./catalogValidation";

const VALID_CATALOG = {
  schemaVersion: 1,
  themes: [
    {
      id: "hooandee-example",
      cssLoaderName: "Hooandee Example",
      name: "Hooandee Example",
      descriptionKey: "themes.example.description",
      author: "Hooandee",
      version: "1.2.3",
      cssLoaderManifestVersion: 9,
      minimumCssLoaderBackendVersion: 9,
      tags: ["library"],
      runtime: {
        moduleId: "example",
        surfaces: ["library", "game-details"],
        capabilities: ["grid-motion"],
      },
      installSource: {
        kind: "css-loader-api",
        baseUrl: "https://themes.example.test",
        themeId: "hooandee-example",
      },
    },
  ],
};

describe("validateThemeCatalog", () => {
  it("accepts a complete versioned catalog", () => {
    const result = validateThemeCatalog(VALID_CATALOG);

    expect(result).toEqual({ ok: true, catalog: VALID_CATALOG });
  });

  it("rejects duplicate stable ids and CSS Loader names", () => {
    const duplicate = {
      ...VALID_CATALOG,
      themes: [VALID_CATALOG.themes[0], { ...VALID_CATALOG.themes[0] }],
    };

    const result = validateThemeCatalog(duplicate);

    expect(result).toEqual({
      ok: false,
      issues: [
        { path: "themes[1].id", code: "duplicate", message: "Duplicate theme id: hooandee-example" },
        { path: "themes[1].cssLoaderName", code: "duplicate", message: "Duplicate CSS Loader name: Hooandee Example" },
      ],
    });
  });

  it("rejects install providers that are not HTTPS", () => {
    const insecure = {
      ...VALID_CATALOG,
      themes: [{
        ...VALID_CATALOG.themes[0],
        installSource: {
          ...VALID_CATALOG.themes[0].installSource,
          baseUrl: "http://themes.example.test",
        },
      }],
    };

    const result = validateThemeCatalog(insecure);

    expect(result).toEqual({
      ok: false,
      issues: [{
        path: "themes[0].installSource.baseUrl",
        code: "invalid_url",
        message: "Install source must use HTTPS",
      }],
    });
  });

  it("rejects unknown runtime surfaces and capabilities", () => {
    const unknownRuntime = {
      ...VALID_CATALOG,
      themes: [{
        ...VALID_CATALOG.themes[0],
        runtime: {
          moduleId: "example",
          surfaces: ["store"],
          capabilities: ["downloaded-javascript"],
        },
      }],
    };

    const result = validateThemeCatalog(unknownRuntime);

    expect(result).toEqual({
      ok: false,
      issues: [
        { path: "themes[0].runtime.surfaces[0]", code: "unsupported", message: "Unsupported runtime surface: store" },
        { path: "themes[0].runtime.capabilities[0]", code: "unsupported", message: "Unsupported runtime capability: downloaded-javascript" },
      ],
    });
  });
});

describe("LOCAL_THEME_CATALOG", () => {
  it("is valid and contains the public themes plus Obsidian Bloom", () => {
    const result = validateThemeCatalog(LOCAL_THEME_CATALOG);

    expect(result.ok).toBe(true);
    expect(LOCAL_THEME_CATALOG.themes.map((theme) => theme.id)).toEqual([
      "hooandee-gallery",
      "hooandee-shattered-realms",
      "hooandee-obsidian-bloom",
    ]);
  });

  it("does not claim an install source before an artifact exists", () => {
    expect(LOCAL_THEME_CATALOG.themes.every((theme) => !("installSource" in theme))).toBe(true);
  });
});
