import { describe, expect, it, vi } from "vitest";

vi.mock("../system/pdcStorage", () => ({
  hydratePrefs: vi.fn(async () => {}),
  onPrefsHealed: vi.fn(() => () => {}),
  prefsHydrated: vi.fn(() => false),
  readString: vi.fn(() => null),
  writeString: vi.fn(),
}));

import { translateForLang } from "./index";

describe("theme translations", () => {
  it.each([
    ["es", "themes.gallery.name", "Hooandee"],
    ["en", "themes.gallery.name", "Hooandee"],
    ["it", "themes.gallery.name", "Hooandee"],
    ["es", "themes.shattered.name", "Reinos Fragmentados"],
    ["en", "themes.shattered.name", "Shattered Realms"],
    ["it", "themes.shattered.name", "Regni Infranti"],
    ["es", "themes.obsidian.name", "Flor de Obsidiana"],
    ["en", "themes.obsidian.name", "Obsidian Bloom"],
    ["it", "themes.obsidian.name", "Fioritura d'Ossidiana"],
    ["es", "themes.state.comingSoon", "Próximamente"],
    ["en", "themes.state.comingSoon", "Coming soon"],
    ["it", "themes.state.comingSoon", "Prossimamente"],
    ["it", "themes.remote.retry", "Controlla aggiornamenti"],
  ] as const)("translates %s/%s", (lang, key, expected) => {
    expect(translateForLang(lang, key)).toBe(expected);
  });

  it("formats local and published theme versions independently", () => {
    expect(translateForLang("es", "themes.version.installed", { version: "v0.7.8" }))
      .toBe("Instalada: v0.7.8");
    expect(translateForLang("en", "themes.version.published", { version: "v0.7.9" }))
      .toBe("Published: v0.7.9");
  });

  it("preserves the complete Italian locale outside the theme surface", () => {
    expect(translateForLang("it", "load.retry")).toBe("Riprova");
  });
});
