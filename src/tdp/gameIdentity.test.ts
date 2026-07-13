import { describe, it, expect } from "vitest";
import { normalizeGameName, isNonSteam, stableGameKey } from "./gameIdentity";

describe("normalizeGameName", () => {
  it("lowercases, trims and collapses whitespace", () => {
    expect(normalizeGameName("  Elden   Ring  ")).toBe("elden ring");
    expect(normalizeGameName("HADES")).toBe("hades");
  });
});

describe("isNonSteam", () => {
  it("is true when app_type is the Shortcut flag", () => {
    expect(isNonSteam({ appid: "42", app_type: 1073741824 })).toBe(true);
  });
  it("is true for a high appid (top bit set) even without app_type", () => {
    expect(isNonSteam({ appid: "3400000000" })).toBe(true);
    expect(isNonSteam({ appid: 2147483648 })).toBe(true);
  });
  it("is false for a normal Steam appid", () => {
    expect(isNonSteam({ appid: "1245620" })).toBe(false);
    expect(isNonSteam({ appid: 570 })).toBe(false);
  });
});

describe("stableGameKey", () => {
  it("keys a Steam game by its numeric appid", () => {
    expect(stableGameKey({ appid: "1245620", display_name: "Elden Ring" })).toBe(
      "1245620",
    );
  });

  it("keys a non-Steam shortcut by normalized name, not the volatile appid", () => {
    expect(
      stableGameKey({
        appid: "3400000000",
        display_name: "Hades",
        app_type: 1073741824,
      }),
    ).toBe("ns:hades");
  });

  it("gives the SAME key when a non-Steam appid changes but the name is stable", () => {
    const a = stableGameKey({ appid: "3400000000", display_name: "My Game", app_type: 1073741824 });
    const b = stableGameKey({ appid: "2900000001", display_name: "My Game", app_type: 1073741824 });
    expect(a).toBe(b);
    expect(a).toBe("ns:my game");
  });

  it("falls back to the raw appid for a non-Steam app with no usable name", () => {
    expect(stableGameKey({ appid: "3400000000", display_name: "", app_type: 1073741824 })).toBe(
      "3400000000",
    );
    expect(stableGameKey({ appid: "3400000000", app_type: 1073741824 })).toBe("3400000000");
  });
});
