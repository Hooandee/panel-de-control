import { describe, it, expect } from "vitest";
import { CATEGORIES, pick } from "./data";

describe("glossary data", () => {
  const terms = CATEGORIES.flatMap((c) => c.terms);

  it("has categories, each with at least one term", () => {
    expect(CATEGORIES.length).toBeGreaterThan(0);
    for (const c of CATEGORIES) expect(c.terms.length).toBeGreaterThan(0);
  });

  it("uses unique category ids", () => {
    const ids = CATEGORIES.map((c) => c.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("uses unique term ids across the whole glossary", () => {
    const ids = terms.map((t) => t.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("uses unique term display names (no two cards titled the same)", () => {
    const names = terms.map((t) => t.term);
    expect(new Set(names).size).toBe(names.length);
  });

  it("has non-empty bilingual text for every category title", () => {
    for (const c of CATEGORIES) {
      expect(c.es.trim()).not.toBe("");
      expect(c.en.trim()).not.toBe("");
    }
  });

  it("has a name and non-empty es/en explanation for every term", () => {
    for (const t of terms) {
      expect(t.term.trim()).not.toBe("");
      expect(t.es.trim()).not.toBe("");
      expect(t.en.trim()).not.toBe("");
    }
  });
});

describe("pick", () => {
  it("returns the matching language", () => {
    const entry = { es: "hola", en: "hi" };
    expect(pick(entry, "es")).toBe("hola");
    expect(pick(entry, "en")).toBe("hi");
  });
});
