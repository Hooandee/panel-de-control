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

    const italianNames = terms.map((t) => t.termIt);
    expect(italianNames.every(Boolean)).toBe(true);
    expect(new Set(italianNames).size).toBe(italianNames.length);

    const germanNames = terms.map((t) => t.termDe);
    expect(germanNames.every(Boolean)).toBe(true);
    expect(new Set(germanNames).size).toBe(germanNames.length);

    const brazilianPortugueseNames = terms.map((t) => t.termPtBR);
    expect(brazilianPortugueseNames.every(Boolean)).toBe(true);
    expect(new Set(brazilianPortugueseNames).size).toBe(brazilianPortugueseNames.length);

    const frenchNames = terms.map((t) => t.termFr);
    expect(frenchNames.every(Boolean)).toBe(true);
    expect(new Set(frenchNames).size).toBe(frenchNames.length);
  });

  it("has non-empty text in every language for each category title", () => {
    for (const c of CATEGORIES) {
      expect(c.es.trim()).not.toBe("");
      expect(c.en.trim()).not.toBe("");
      expect(c.it.trim()).not.toBe("");
      expect(c.de.trim()).not.toBe("");
      expect(c.ptBR.trim()).not.toBe("");
      expect(c.fr.trim()).not.toBe("");
    }
  });

  it("has a name and non-empty explanation in every language for each term", () => {
    for (const t of terms) {
      expect(t.term.trim()).not.toBe("");
      expect(t.es.trim()).not.toBe("");
      expect(t.en.trim()).not.toBe("");
      expect(t.it.trim()).not.toBe("");
      expect(t.de.trim()).not.toBe("");
      expect(t.ptBR.trim()).not.toBe("");
      expect(t.fr.trim()).not.toBe("");
    }
  });

  it("does not use em dashes in Italian text", () => {
    const italian = CATEGORIES.flatMap((category) => [
      category.it,
      ...category.terms.flatMap((term) => [term.termIt, term.it]),
    ]);

    expect(italian.some((value) => value.includes("—"))).toBe(false);
  });

  it("does not use em dashes in Brazilian Portuguese text", () => {
    const brazilianPortuguese = CATEGORIES.flatMap((category) => [
      category.ptBR,
      ...category.terms.flatMap((term) => [term.termPtBR, term.ptBR]),
    ]);

    expect(brazilianPortuguese.some((value) => value.includes("—"))).toBe(false);
  });

  it("does not use em dashes in French text", () => {
    const french = CATEGORIES.flatMap((category) => [
      category.fr,
      ...category.terms.flatMap((term) => [term.termFr, term.fr]),
    ]);

    expect(french.some((value) => value.includes("—"))).toBe(false);
  });
});

describe("pick", () => {
  it("returns the matching language", () => {
    const entry = { es: "hola", en: "hi", it: "ciao", de: "hallo", ptBR: "olá", fr: "salut" };
    expect(pick(entry, "es")).toBe("hola");
    expect(pick(entry, "en")).toBe("hi");
    expect(pick(entry, "it")).toBe("ciao");
    expect(pick(entry, "de")).toBe("hallo");
    expect(pick(entry, "pt-BR")).toBe("olá");
    expect(pick(entry, "fr")).toBe("salut");
  });
});
