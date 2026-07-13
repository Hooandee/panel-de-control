import { describe, it, expect } from "vitest";
import { isNonSteamKey, nonSteamName, configuredSections } from "./gameProfiles";
import type { GameProfileRow } from "../api";

describe("isNonSteamKey / nonSteamName", () => {
  it("detects and unwraps a non-Steam key", () => {
    expect(isNonSteamKey("ns:hades")).toBe(true);
    expect(nonSteamName("ns:hades")).toBe("hades");
  });
  it("treats a numeric Steam appid as Steam", () => {
    expect(isNonSteamKey("1245620")).toBe(false);
  });
});

describe("configuredSections", () => {
  it("returns only the present sections, in display order", () => {
    const row: GameProfileRow = {
      appid: "1245620",
      cpu: { smt: false, boost: true, cores: null, follows_global: false },
      tdp: { pl1: 22, auto: false, gpu: false, follows_global: false },
    };
    expect(configuredSections(row)).toEqual(["tdp", "cpu"]);
  });
  it("is empty when nothing is configured", () => {
    expect(configuredSections({ appid: "x" })).toEqual([]);
  });
});
