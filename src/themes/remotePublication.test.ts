import { describe, expect, it } from "vitest";

import { parseThemePublication } from "./remotePublication";

const PUBLISHED = {
  status: "published",
  checkedAt: 100,
  themes: [{
    catalogId: "hooandee-gallery",
    cssLoaderName: "Hooandee Gallery",
    publishedVersion: "0.7.9",
    compatibility: "compatible",
    notes: { es: "Novedades", en: "Changes", it: "Novità" },
  }],
};

describe("parseThemePublication", () => {
  it("accepts a bounded publication without transport fields", () => {
    expect(parseThemePublication(PUBLISHED)).toEqual(PUBLISHED);
  });

  it.each([
    { ...PUBLISHED, extra: true },
    { ...PUBLISHED, checkedAt: Number.NaN },
    { ...PUBLISHED, themes: [{ ...PUBLISHED.themes[0], artifactUrl: "https://attacker.invalid" }] },
    { ...PUBLISHED, themes: [{ ...PUBLISHED.themes[0], publishedVersion: "v0.7.9" }] },
    { ...PUBLISHED, themes: [{ ...PUBLISHED.themes[0], compatibility: "probably" }] },
    { ...PUBLISHED, themes: [{ ...PUBLISHED.themes[0], notes: { fr: "Non" } }] },
    { ...PUBLISHED, themes: [{ ...PUBLISHED.themes[0], notes: { es: "x".repeat(1_001) } }] },
  ])("rejects hostile or ambiguous published payloads", (payload) => {
    expect(() => parseThemePublication(payload)).toThrow();
  });

  it("accepts disabled and stable sanitized failures only", () => {
    expect(parseThemePublication({ status: "disabled" })).toEqual({ status: "disabled" });
    expect(parseThemePublication({
      status: "temporarily-unavailable",
      code: "offline",
      retryable: true,
    })).toEqual({ status: "temporarily-unavailable", code: "offline", retryable: true });
    expect(() => parseThemePublication({
      status: "recoverable-failure",
      code: "raw-python-error",
      retryable: true,
    })).toThrow();
  });

  it("rejects duplicate catalog identities", () => {
    expect(() => parseThemePublication({
      ...PUBLISHED,
      themes: [PUBLISHED.themes[0], PUBLISHED.themes[0]],
    })).toThrow();
  });
});
