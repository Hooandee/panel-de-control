import { describe, expect, it } from "vitest";

import { LOCAL_THEME_CATALOG } from "./catalog";
import type { CssLoaderSnapshot, CssLoaderTheme } from "./cssLoaderTypes";
import type { ThemePublicationState } from "./remotePublication";
import { deriveThemeCards } from "./state";

function installedTheme(name: string, version: string, enabled: boolean): CssLoaderTheme {
  return {
    id: name,
    name,
    displayName: name,
    version,
    author: "Hooandee",
    enabled,
    patches: [],
  };
}

function ready(themes: CssLoaderTheme[]): CssLoaderSnapshot {
  return { status: "ready", backendVersion: 9, themes };
}

function publication(
  version: string,
  compatibility: "compatible" | "incompatible-panel" | "incompatible-css-loader" = "compatible",
): ThemePublicationState {
  return {
    status: "published",
    checkedAt: 100,
    themes: [{
      catalogId: "hooandee-gallery",
      cssLoaderName: "Hooandee Gallery",
      publishedVersion: version,
      compatibility,
      notes: { es: "Novedades" },
    }],
  };
}

describe("deriveThemeCards", () => {
  it("keeps every catalog theme visible when CSS Loader is missing", () => {
    const cards = deriveThemeCards(LOCAL_THEME_CATALOG, { status: "missing", themes: [] });

    expect(cards.map((card) => [card.id, card.installed, card.active])).toEqual([
      ["hooandee-gallery", false, false],
      ["hooandee-shattered-realms", false, false],
      ["hooandee-obsidian-bloom", false, false],
    ]);
  });

  it("matches installed and active state only by the catalog CSS Loader identity", () => {
    const cards = deriveThemeCards(LOCAL_THEME_CATALOG, ready([
      installedTheme("Hooandee Gallery", "0.7.8", true),
      installedTheme("Theme with Gallery in its title", "9.0.0", true),
    ]));

    expect(cards.find((card) => card.id === "hooandee-gallery")).toMatchObject({
      installed: true,
      active: true,
      installedVersion: "0.7.8",
      updateAvailable: false,
    });
    expect(cards.find((card) => card.id === "hooandee-shattered-realms")?.installed).toBe(false);
  });

  it("reports an update only for a valid older semantic version", () => {
    const cards = deriveThemeCards(LOCAL_THEME_CATALOG, ready([
      installedTheme("Hooandee Gallery", "0.5.9", false),
      installedTheme("Hooandee Shattered Realms", "development", false),
    ]));

    expect(cards.find((card) => card.id === "hooandee-gallery")?.updateAvailable).toBe(true);
    expect(cards.find((card) => card.id === "hooandee-shattered-realms")?.updateAvailable).toBe(false);
  });

  it("accepts CSS Loader's conventional v-prefixed theme versions", () => {
    const cards = deriveThemeCards(LOCAL_THEME_CATALOG, ready([
      installedTheme("Hooandee Gallery", "v0.7.8", false),
      installedTheme("Hooandee Shattered Realms", "v0.3.9", false),
    ]));

    expect(cards.find((card) => card.id === "hooandee-gallery")?.updateAvailable).toBe(false);
    expect(cards.find((card) => card.id === "hooandee-shattered-realms")?.updateAvailable).toBe(false);
  });

  it("orders semantic prereleases by numeric and lexical identifiers", () => {
    const catalog = {
      ...LOCAL_THEME_CATALOG,
      themes: LOCAL_THEME_CATALOG.themes.map((theme) => theme.id === "hooandee-gallery"
        ? { ...theme, includedVersion: "0.6.0-beta.10" }
        : theme),
    };

    const cards = deriveThemeCards(catalog, ready([
      installedTheme("Hooandee Gallery", "0.6.0-beta.2", false),
    ]));

    expect(cards.find((card) => card.id === "hooandee-gallery")?.updateAvailable).toBe(true);
  });

  it("compares semantic version numbers without JavaScript rounding", () => {
    const cards = deriveThemeCards(
      LOCAL_THEME_CATALOG,
      ready([installedTheme(
        "Hooandee Gallery",
        "9007199254740992.0.0",
        false,
      )]),
      publication("9007199254740993.0.0"),
    );

    expect(cards.find((card) => card.id === "hooandee-gallery")).toMatchObject({
      targetVersion: "9007199254740993.0.0",
      versionRelation: "update-available",
      updateAvailable: true,
    });
  });

  it("keeps local activation while exposing a compatible official update separately", () => {
    const cards = deriveThemeCards(
      LOCAL_THEME_CATALOG,
      ready([installedTheme("Hooandee Gallery", "0.7.8", true)]),
      publication("0.7.9"),
    );

    expect(cards.find((card) => card.id === "hooandee-gallery")).toMatchObject({
      installed: true,
      active: true,
      installedVersion: "0.7.8",
      publishedVersion: "0.7.9",
      updateAvailable: true,
      targetVersion: "0.7.9",
      preferredInstallSource: "official-remote",
      versionRelation: "update-available",
    });
  });

  it("prefers the bundled source for a first install even when a newer release exists", () => {
    const cards = deriveThemeCards(LOCAL_THEME_CATALOG, ready([]), publication("0.7.9"));

    expect(cards.find((card) => card.id === "hooandee-gallery")).toMatchObject({
      installed: false,
      publishedVersion: "0.7.9",
      updateAvailable: false,
      targetVersion: "0.7.8",
      preferredInstallSource: "bundled",
      versionRelation: "not-installed",
    });
  });

  it("does not let an incompatible publication hide the usable bundled package", () => {
    const cards = deriveThemeCards(
      LOCAL_THEME_CATALOG,
      ready([installedTheme("Hooandee Gallery", "0.7.7", false)]),
      publication("0.7.9", "incompatible-css-loader"),
    );

    expect(cards.find((card) => card.id === "hooandee-gallery")).toMatchObject({
      publishedVersion: "0.7.9",
      publicationCompatibility: "incompatible-css-loader",
      updateAvailable: true,
      targetVersion: "0.7.8",
      preferredInstallSource: "bundled",
    });
  });

  it("reports a local-newer install without offering a downgrade", () => {
    const cards = deriveThemeCards(
      LOCAL_THEME_CATALOG,
      ready([installedTheme("Hooandee Gallery", "0.8.0", false)]),
      publication("0.7.9"),
    );

    expect(cards.find((card) => card.id === "hooandee-gallery")).toMatchObject({
      updateAvailable: false,
      versionRelation: "local-newer",
    });
  });
});
