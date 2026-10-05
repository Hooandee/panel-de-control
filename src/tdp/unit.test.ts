import { describe, expect, it } from "vitest";

import { isLevelUnit, levelFrequencySummary } from "./unit";

describe("power unit helpers", () => {
  it("recognises the ARM level unit only", () => {
    expect(isLevelUnit("level")).toBe(true);
    expect(isLevelUnit("W")).toBe(false);
    expect(isLevelUnit(undefined)).toBe(false);
  });

  it("summarises the real cluster and GPU ceilings of a level", () => {
    expect(levelFrequencySummary({ cpu_khz: [1459200, 2054400, 2227200], gpu_mhz: 475 }))
      .toBe("CPU 1.5 · 2.1 · 2.2 GHz  ·  GPU 475 MHz");
    expect(levelFrequencySummary({ cpu_khz: [2016000], gpu_mhz: null })).toBe("CPU 2.0 GHz");
    expect(levelFrequencySummary(null)).toBeNull();
  });
});
