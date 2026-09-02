import { describe, expect, it, vi } from "vitest";

vi.mock("../system/pdcStorage", () => ({
  hydratePrefs: vi.fn(async () => {}), onPrefsHealed: vi.fn(() => () => {}),
  prefsHydrated: vi.fn(() => false), readString: vi.fn(() => null), writeString: vi.fn(),
}));

import { DICTS, translateForLang } from "./index";

const GENERIC_THEME_NAMESPACES = new Set([
  "action", "catalog", "cssLoader", "delete", "details", "engine", "group", "install", "loading",
  "operation", "patches", "recovery", "remote", "retry", "state", "title",
  "update", "version",
]);

describe("theme translations", () => {
  it.each([
    ["es", "themes.catalog.empty", "Ahora mismo no hay temas publicados."],
    ["en", "themes.catalog.empty", "There are no published themes right now."],
    ["it", "themes.catalog.empty", "Al momento non ci sono temi pubblicati."],
    ["es", "themes.cssLoader.openStore", "Abrir tienda de Decky"],
    ["en", "themes.remote.cached", "Offline. Showing the last verified catalog saved on this device."],
    ["it", "themes.remote.retry", "Controlla aggiornamenti"],
  ] as const)("translates %s/%s", (lang, key, expected) => {
    expect(translateForLang(lang, key)).toBe(expected);
  });

  it("contains only generic theme UI namespaces", () => {
    for (const dictionary of Object.values(DICTS)) {
      expect(Object.keys(dictionary)
        .filter((key) => key.startsWith("themes."))
        .map((key) => key.split(".")[1])
        .filter((namespace) => !GENERIC_THEME_NAMESPACES.has(namespace)))
        .toEqual([]);
    }
  });

  it("formats installed and published versions independently", () => {
    expect(translateForLang("es", "themes.version.installed", { version: "v1.2.2" }))
      .toBe("Instalada: v1.2.2");
    expect(translateForLang("en", "themes.version.published", { version: "v1.2.3" }))
      .toBe("Published: v1.2.3");
  });

  it.each([
    ["es", "themes.remote.card.version", { version: "1.2.3" }, "Versión: v1.2.3"],
    ["en", "themes.remote.card.update", { version: "1.2.3" }, "Update: v1.2.3"],
    ["it", "themes.install.confirm.title", { name: "HOOANDEE" }, "Installare HOOANDEE?"],
    ["it", "themes.delete.confirm.title", { name: "HOOANDEE" }, "Rimuovere HOOANDEE?"],
  ] as const)("formats simplified theme copy in %s", (lang, key, values, expected) => {
    expect(translateForLang(lang, key, values)).toBe(expected);
  });
});
