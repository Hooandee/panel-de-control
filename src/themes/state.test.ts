import { describe, expect, it } from "vitest";

import { LOCAL_THEME_CATALOG } from "./catalog";
import type { CssLoaderSnapshot, CssLoaderTheme } from "./cssLoaderTypes";
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
      installedTheme("Hooandee Gallery", "0.6.0", true),
      installedTheme("Theme with Gallery in its title", "9.0.0", true),
    ]));

    expect(cards.find((card) => card.id === "hooandee-gallery")).toMatchObject({
      installed: true,
      active: true,
      installedVersion: "0.6.0",
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
      installedTheme("Hooandee Gallery", "v0.6.0", false),
      installedTheme("Hooandee Shattered Realms", "v0.3.9", false),
    ]));

    expect(cards.find((card) => card.id === "hooandee-gallery")?.updateAvailable).toBe(false);
    expect(cards.find((card) => card.id === "hooandee-shattered-realms")?.updateAvailable).toBe(true);
  });
});
