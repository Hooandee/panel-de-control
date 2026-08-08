import { describe, expect, it } from "vitest";

import { clampCpuWindow, formatCpuFrequency } from "./cpu";


describe("CPU frequency controls", () => {
  it("formats exact server readback in GHz with two decimals", () => {
    expect(formatCpuFrequency(2_400_000, "es")).toBe("2,40 GHz");
    expect(formatCpuFrequency(2_400_000, "en")).toBe("2.40 GHz");
    expect(formatCpuFrequency(2_400_000, "it")).toBe("2,40 GHz");
    expect(formatCpuFrequency(null, "es")).toBe("—");
  });

  it("clamps a crossed minimum to the selected maximum", () => {
    expect(clampCpuWindow(2_600_000, 2_400_000, 800_000, 3_500_000)).toEqual([
      2_400_000, 2_400_000,
    ]);
  });

  it("clamps both values to the hardware envelope", () => {
    expect(clampCpuWindow(300_000, 3_800_000, 800_000, 3_500_000)).toEqual([
      800_000, 3_500_000,
    ]);
  });
});
