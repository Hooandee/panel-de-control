import { describe, expect, it, vi } from "vitest";

vi.mock("../system/pdcStorage", () => ({
  hydratePrefs: vi.fn(async () => {}),
  onPrefsHealed: vi.fn(() => () => {}),
  prefsHydrated: vi.fn(() => false),
  readString: vi.fn(() => null),
  writeString: vi.fn(),
}));

import { translateForLang } from "./index";

describe("report translations", () => {
  it.each([
    ["es", "Temas"],
    ["en", "Themes"],
    ["it", "Temi"],
  ] as const)("translates the themes category in %s", (lang, expected) => {
    expect(translateForLang(lang, "report.cat.themes")).toBe(expected);
  });

  it.each([
    ["es", "Una petición o idea", "Esto no es un fallo."],
    ["en", "A request or idea", "This is not a bug report."],
    ["it", "Una richiesta o un'idea", "Questa non è una segnalazione di errore."],
    ["de", "Einen Wunsch oder eine Idee", "Das ist keine Fehlermeldung."],
  ] as const)("makes feature requests explicit in %s", (lang, label, explanation) => {
    expect(translateForLang(lang, "report.kind.feature")).toBe(label);
    expect(translateForLang(lang, "report.intro.feature")).toContain(explanation);
  });
});
