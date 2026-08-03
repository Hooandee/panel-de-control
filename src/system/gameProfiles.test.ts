import { describe, it, expect } from "vitest";
import { configuredSections } from "./gameProfiles";
import type { GameProfileRow } from "../api";

describe("configuredSections", () => {
  it("returns only the present sections, in display order", () => {
    const row: GameProfileRow = {
      appid: "1245620",
      cpu: { smt: false, boost: true, cores: null, follows_global: false },
      tdp: { pl1: 22, auto: false, follows_global: false },
      gpu: { manual: true, min: 800, max: 2_000, follows_global: false },
    };
    expect(configuredSections(row)).toEqual(["tdp", "cpu", "gpu"]);
  });
  it("is empty when nothing is configured", () => {
    expect(configuredSections({ appid: "x" })).toEqual([]);
  });
});
