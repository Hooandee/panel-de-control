import { describe, it, expect } from "vitest";
import { steamLangToLang } from "./detect";

describe("steamLangToLang (seed the default from Steam's UI language)", () => {
  it("maps English to en", () => {
    expect(steamLangToLang("english")).toBe("en");
    expect(steamLangToLang("English")).toBe("en");
    expect(steamLangToLang("  ENGLISH  ")).toBe("en");
    expect(steamLangToLang("en")).toBe("en");
  });

  it("maps Spanish and its variants to es", () => {
    expect(steamLangToLang("spanish")).toBe("es");
    expect(steamLangToLang("latam")).toBe("es");
  });

  it("maps Italian and its language code to it", () => {
    expect(steamLangToLang("italian")).toBe("it");
    expect(steamLangToLang("Italian")).toBe("it");
    expect(steamLangToLang("  ITALIAN  ")).toBe("it");
    expect(steamLangToLang("it")).toBe("it");
  });

  it("maps German and its language code to de", () => {
    expect(steamLangToLang("german")).toBe("de");
    expect(steamLangToLang("German")).toBe("de");
    expect(steamLangToLang("  GERMAN  ")).toBe("de");
    expect(steamLangToLang("de")).toBe("de");
  });

  it("maps only Brazilian Portuguese identifiers to pt-BR", () => {
    expect(steamLangToLang("brazilian")).toBe("pt-BR");
    expect(steamLangToLang("Brazilian Portuguese")).toBe("pt-BR");
    expect(steamLangToLang("pt-BR")).toBe("pt-BR");
    expect(steamLangToLang("portuguese")).toBe("es");
    expect(steamLangToLang("pt-PT")).toBe("es");
    expect(steamLangToLang("brazilian portuguese beta")).toBe("es");
  });

  it("maps any other language to es (our default)", () => {
    expect(steamLangToLang("schinese")).toBe("es");
  });

  it("degrades to es for null/blank/garbage", () => {
    expect(steamLangToLang(null)).toBe("es");
    expect(steamLangToLang(undefined)).toBe("es");
    expect(steamLangToLang("")).toBe("es");
    expect(steamLangToLang("   ")).toBe("es");
  });
});
