import { describe, expect, it } from "vitest";

import { gpuClockPresentation, nearestLevelIndex } from "./logic";

describe("gpuClockPresentation", () => {
  it("uses confirmed readback instead of configured values after rejection", () => {
    const shown = gpuClockPresentation({
      manual: true,
      min: 1_200,
      max: 2_400,
      range_min: 200,
      range_max: 2_700,
      applied_min: 300,
      applied_max: 2_000,
      status: "rejected",
    });

    expect(shown).toEqual({ minimum: 300, maximum: 2_000, rejected: true });
  });

  it("uses the configured manual window after confirmed application", () => {
    const shown = gpuClockPresentation({
      manual: true,
      min: 1_200,
      max: 2_400,
      range_min: 200,
      range_max: 2_700,
      applied_min: 1_200,
      applied_max: 2_400,
      status: "applied",
    });

    expect(shown).toEqual({ minimum: 1_200, maximum: 2_400, rejected: false });
  });
});

describe("nearestLevelIndex", () => {
  const levels = [220, 295, 348, 401, 475, 550, 615, 680];
  it("maps a stored MHz value onto the closest real level", () => {
    expect(nearestLevelIndex(levels, 220)).toBe(0);
    expect(nearestLevelIndex(levels, 520)).toBe(5);
    expect(nearestLevelIndex(levels, 680)).toBe(7);
    expect(nearestLevelIndex(levels, 9999)).toBe(7);
  });
});
