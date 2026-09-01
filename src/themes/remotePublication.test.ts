import { describe, expect, it } from "vitest";

import { localizePublishedText, parseThemePublication } from "./remotePublication";

const THEME = {
  catalogId: "example-theme",
  cssLoaderName: "Example Theme",
  publishedVersion: "1.2.3",
  displayName: { es: "Tema de ejemplo", en: "Example Theme", it: "Tema di esempio" },
  description: { es: "Descripcion", en: "Description", it: "Descrizione" },
  author: "Example Author",
  tags: ["dark", "compact"],
  notes: { es: "Novedades", en: "Changes", it: "Novita" },
  compatibility: "compatible",
  exclusiveGroup: "interface",
};

describe("parseThemePublication", () => {
  it.each(["published", "cached"] as const)("accepts a sanitized %s catalog", (status) => {
    const payload = {
      status,
      checkedAt: 100,
      themes: [THEME],
      ...(status === "cached" ? { code: "offline", retryable: true } : {}),
    };

    expect(parseThemePublication(payload)).toEqual(payload);
  });

  it("requires exact presentation locales and rejects transport or unknown fields", () => {
    for (const theme of [
      { ...THEME, displayName: { en: "Example Theme", es: "Tema" } },
      { ...THEME, description: { ...THEME.description, fr: "Description" } },
      { ...THEME, artifactUrl: "https://attacker.invalid/theme.zip" },
      { ...THEME, runtime: { moduleId: "downloaded-code" } },
      { ...THEME, publishedVersion: "v1.2.3" },
      { ...THEME, notes: { en: "Changes" } },
      { ...THEME, cssLoaderName: "Example/Theme" },
      { ...THEME, cssLoaderName: "Example\\Theme" },
    ]) {
      expect(() => parseThemePublication({ status: "published", checkedAt: 100, themes: [theme] }))
        .toThrow();
    }
  });

  it("accepts releases without notes as an exact empty object", () => {
    const theme = { ...THEME, notes: {} };
    expect(parseThemePublication({ status: "published", checkedAt: 100, themes: [theme] }))
      .toMatchObject({ themes: [{ notes: {} }] });
  });

  it("applies the publishing contract bounds in Unicode code points", () => {
    const accepted = {
      ...THEME,
      displayName: { ...THEME.displayName, en: "😀".repeat(80) },
      description: { ...THEME.description, en: "😀".repeat(400) },
      author: "😀".repeat(80),
      tags: Array.from({ length: 8 }, (_, index) => `tag-${index}`),
    };
    expect(() => parseThemePublication({ status: "published", checkedAt: 100, themes: [accepted] }))
      .not.toThrow();
    for (const theme of [
      { ...accepted, displayName: { ...accepted.displayName, en: "😀".repeat(81) } },
      { ...accepted, description: { ...accepted.description, en: "😀".repeat(401) } },
      { ...accepted, author: "😀".repeat(81) },
      { ...accepted, tags: [...accepted.tags, "tag-8"] },
    ]) {
      expect(() => parseThemePublication({ status: "published", checkedAt: 100, themes: [theme] }))
        .toThrow();
    }
  });

  it("rejects duplicate catalog and CSS Loader identities", () => {
    expect(() => parseThemePublication({
      status: "published",
      checkedAt: 100,
      themes: [THEME, { ...THEME, catalogId: "second-theme" }],
    })).toThrow();
    expect(() => parseThemePublication({
      status: "published",
      checkedAt: 100,
      themes: [THEME, { ...THEME, cssLoaderName: "Second Theme" }],
    })).toThrow();
  });

  it("requires typed cached failure metadata", () => {
    expect(() => parseThemePublication({
      status: "cached", checkedAt: 100, themes: [THEME], code: "private-error", retryable: true,
    })).toThrow();
    expect(() => parseThemePublication({
      status: "cached", checkedAt: 100, themes: [THEME], code: "offline", retryable: "yes",
    })).toThrow();
  });
});

describe("localizePublishedText", () => {
  it("uses current locale then English, Spanish and Italian without i18n lookup", () => {
    expect(localizePublishedText({ es: "ES", en: "EN", it: "IT" }, "it")).toBe("IT");
    expect(localizePublishedText({ es: "ES", en: "", it: "IT" }, "en")).toBe("ES");
    expect(localizePublishedText({ es: "", en: "", it: "IT" }, "es")).toBe("IT");
  });
});
