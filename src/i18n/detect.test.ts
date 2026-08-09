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

  it("maps any other language to es (our default)", () => {
    expect(steamLangToLang("german")).toBe("es");
    expect(steamLangToLang("brazilian")).toBe("es");
    expect(steamLangToLang("schinese")).toBe("es");
  });

  it("degrades to es for null/blank/garbage", () => {
    expect(steamLangToLang(null)).toBe("es");
    expect(steamLangToLang(undefined)).toBe("es");
    expect(steamLangToLang("")).toBe("es");
    expect(steamLangToLang("   ")).toBe("es");
  });
});
