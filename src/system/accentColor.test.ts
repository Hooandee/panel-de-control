import { describe, it, expect } from "vitest";
import { ACCENTS, DEFAULT_ACCENT, resolveAccent, hexToRgbTriplet } from "./accentColor";

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
