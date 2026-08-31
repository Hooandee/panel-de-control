import { describe, expect, it } from "vitest";

import { LOCAL_THEME_CATALOG } from "./catalog";
import { validateThemeCatalog } from "./catalogValidation";

const VALID_CATALOG = {
  schemaVersion: 1,
  themes: [
    {
      id: "hooandee-example",
      cssLoaderName: "Hooandee Example",
      nameKey: "themes.example.name",
      descriptionKey: "themes.example.description",
      availability: "available",
      author: "Hooandee",
      includedVersion: "1.2.3",
      cssLoaderManifestVersion: 9,
      minimumCssLoaderBackendVersion: 9,
      tags: ["library"],
      runtime: {
        moduleId: "example",
        surfaces: ["library", "game-details"],
        capabilities: ["grid-motion"],
      },
      installSources: [
        {
          kind: "bundled",
          packageId: "hooandee-example",
        },
        {
          kind: "official-remote",
          channelId: "panel-pages-v1",
        },
      ],
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

  it("rejects install package ids that are not stable slugs", () => {
    const invalid = {
      ...VALID_CATALOG,
      themes: [{
        ...VALID_CATALOG.themes[0],
        installSources: [{
          kind: "bundled",
          packageId: "../example",
        }],
      }],
    };

    const result = validateThemeCatalog(invalid);

    expect(result).toEqual({
      ok: false,
      issues: [{
        path: "themes[0].installSources[0].packageId",
        code: "invalid",
        message: "Bundled package id must be a stable slug",
      }],
    });
  });

  it("rejects a bundled package registered under a different catalog id", () => {
    const mismatch = {
      ...VALID_CATALOG,
      themes: [{
        ...VALID_CATALOG.themes[0],
        installSources: [{
          kind: "bundled",
          packageId: "hooandee-other",
        }],
      }],
    };

    expect(validateThemeCatalog(mismatch)).toEqual({
      ok: false,
      issues: [{
        path: "themes[0].installSources[0].packageId",
        code: "invalid",
        message: "Bundled package id must match its catalog id",
      }],
    });
  });

  it("rejects transport fields embedded in the fixed official channel", () => {
    const invalid = {
      ...VALID_CATALOG,
      themes: [{
        ...VALID_CATALOG.themes[0],
        installSources: [{
          kind: "official-remote",
          channelId: "panel-pages-v1",
          baseUrl: "https://attacker.invalid/themes",
        }],
        includedVersion: undefined,
      }],
    };

    expect(validateThemeCatalog(invalid)).toEqual({
      ok: false,
      issues: [{
        path: "themes[0].installSources[0].baseUrl",
        code: "unsupported",
        message: "Install source contains an unsupported field: baseUrl",
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

  it("rejects unknown availability and contradictory coming-soon packages", () => {
    const invalid = {
      ...VALID_CATALOG,
      themes: [{
        ...VALID_CATALOG.themes[0],
        availability: "coming-soon",
      }, {
        ...VALID_CATALOG.themes[0],
        id: "hooandee-future",
        cssLoaderName: "Hooandee Future",
        nameKey: "themes.future.name",
        availability: "future",
        includedVersion: undefined,
        installSources: [],
      }],
    };

    expect(validateThemeCatalog(invalid)).toEqual({
      ok: false,
      issues: [
        {
          path: "themes[0].installSources",
          code: "invalid",
          message: "Coming-soon themes cannot declare install sources",
        },
        {
          path: "themes[1].availability",
          code: "unsupported",
          message: "Unsupported theme availability: future",
        },
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

  it("exposes only Gallery as a package bundled and verified by Panel", () => {
    expect(LOCAL_THEME_CATALOG.themes.map((theme) => [
      theme.id,
      theme.installSources,
      "includedVersion" in theme ? theme.includedVersion : null,
    ])).toEqual([
      ["hooandee-gallery", [
        { kind: "bundled", packageId: "hooandee-gallery" },
        { kind: "official-remote", channelId: "panel-pages-v1" },
      ], "0.7.8"],
      ["hooandee-shattered-realms", [], null],
      ["hooandee-obsidian-bloom", [], null],
    ]);
  });

  it("exposes only Hooandee as available in Panel", () => {
    expect(LOCAL_THEME_CATALOG.themes.map((theme) => [theme.id, theme.availability, theme.nameKey]))
      .toEqual([
        ["hooandee-gallery", "available", "themes.gallery.name"],
        ["hooandee-shattered-realms", "coming-soon", "themes.shattered.name"],
        ["hooandee-obsidian-bloom", "coming-soon", "themes.obsidian.name"],
      ]);
  });

  it("declares Gallery's native surface isolation runtime", () => {
    expect(LOCAL_THEME_CATALOG.themes.find((theme) => theme.id === "hooandee-gallery")?.runtime)
      .toEqual({
        moduleId: "gallery",
        surfaces: ["library", "library-grid", "game-details", "settings"],
        capabilities: ["surface-isolation", "performance-budget"],
      });
  });
});
