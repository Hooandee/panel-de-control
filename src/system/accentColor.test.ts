import { describe, it, expect } from "vitest";
import { ACCENTS, DEFAULT_ACCENT, THEME_ACCENT_ID, applyAccentId, applyThemeAccent, currentAccentHex, currentAccentRgb, parseRgbTriplet, resolveAccent, resolveAccentSelection, hexToRgbTriplet } from "./accentColor";

describe("accent palette", () => {
  it("defaults to blue", () => {
    expect(DEFAULT_ACCENT.id).toBe("blue");
    expect(DEFAULT_ACCENT.hex.toLowerCase()).toBe("#4ea1ff");
  });

  it("has unique ids and valid 6-digit hex colours", () => {
    const ids = ACCENTS.map((a) => a.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const a of ACCENTS) expect(a.hex).toMatch(/^#[0-9a-fA-F]{6}$/);
  });
});

describe("resolveAccent", () => {
  it("returns the matching entry", () => {
    expect(resolveAccent("green").id).toBe("green");
  });

  it("falls back to the default for unknown / null ids", () => {
    expect(resolveAccent("does-not-exist")).toBe(DEFAULT_ACCENT);
    expect(resolveAccent(null)).toBe(DEFAULT_ACCENT);
    expect(resolveAccent(undefined)).toBe(DEFAULT_ACCENT);
  });
});

describe("hexToRgbTriplet", () => {
  it("converts a hex to comma-separated components", () => {
    expect(hexToRgbTriplet("#4ea1ff")).toBe("78,161,255");
  });

  it("tolerates a missing hash", () => {
    expect(hexToRgbTriplet("3fbf6f")).toBe("63,191,111");
  });

  it("falls back to the blue triplet for a non-hex value", () => {
    expect(hexToRgbTriplet("var(--x)")).toBe("78,161,255");
  });
});

describe("theme-driven default accent", () => {
  it("parses rgb triplets in the forms themes write", () => {
    expect(parseRgbTriplet("95, 242, 176")).toBe("95,242,176");
    expect(parseRgbTriplet(" 255 118 84 ")).toBe("255,118,84");
    expect(parseRgbTriplet("300, 0, 0")).toBeNull();
    expect(parseRgbTriplet("#ff0000")).toBeNull();
    expect(parseRgbTriplet("")).toBeNull();
  });

  it("treats an unset or unknown selection as default", () => {
    expect(resolveAccentSelection(null)).toBe(THEME_ACCENT_ID);
    expect(resolveAccentSelection("nope")).toBe(THEME_ACCENT_ID);
    expect(resolveAccentSelection("green")).toBe("green");
  });

  it("follows the theme accent only while default is selected", () => {
    applyAccentId(THEME_ACCENT_ID);
    applyThemeAccent(null);
    expect(currentAccentHex()).toBe(DEFAULT_ACCENT.hex);
    applyThemeAccent("255, 118, 84");
    expect(currentAccentHex()).toBe("#ff7654");
    expect(currentAccentRgb()).toBe("255,118,84");
    applyAccentId("green");
    expect(currentAccentHex()).toBe(resolveAccent("green").hex);
    applyThemeAccent("1, 2, 3");
    expect(currentAccentHex()).toBe(resolveAccent("green").hex);
    applyAccentId(THEME_ACCENT_ID);
    expect(currentAccentHex()).toBe("#010203");
    applyThemeAccent(null);
  });
});
