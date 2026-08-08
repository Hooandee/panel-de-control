import { describe, it, expect } from "vitest";
import { CATEGORIES, pick, pickTerm, type GlossaryTerm } from "./data";

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

    const italianNames = terms.map((t) => t.termIt);
    expect(italianNames.every(Boolean)).toBe(true);
    expect(new Set(italianNames).size).toBe(italianNames.length);
  });

  it("has non-empty text in every language for each category title", () => {
    for (const c of CATEGORIES) {
      expect(c.es.trim()).not.toBe("");
      expect(c.en.trim()).not.toBe("");
      expect(c.it.trim()).not.toBe("");
    }
  });

  it("has a name and non-empty explanation in every language for each term", () => {
    for (const t of terms) {
      expect(t.term.trim()).not.toBe("");
      expect(t.es.trim()).not.toBe("");
      expect(t.en.trim()).not.toBe("");
      expect(t.it.trim()).not.toBe("");
    }
  });

  it("does not use em dashes in Italian text", () => {
    const italian = CATEGORIES.flatMap((category) => [
      category.it,
      ...category.terms.flatMap((term) => [term.termIt, term.it]),
    ]);

    expect(italian.some((value) => value.includes("—"))).toBe(false);
  });
});

describe("pick", () => {
  it("returns the matching language", () => {
    const entry = { es: "hola", en: "hi", it: "ciao" };
    expect(pick(entry, "es")).toBe("hola");
    expect(pick(entry, "en")).toBe("hi");
    expect(pick(entry, "it")).toBe("ciao");
  });

  it("uses the Italian display term without changing Spanish or English", () => {
    const entry: GlossaryTerm = {
      id: "battery",
      term: "Salud de la batería",
      termIt: "Stato della batteria",
      es: "estado",
      en: "health",
      it: "stato",
    };

    expect(pickTerm(entry, "es")).toBe("Salud de la batería");
    expect(pickTerm(entry, "en")).toBe("Salud de la batería");
    expect(pickTerm(entry, "it")).toBe("Stato della batteria");
  });
});
