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
});
