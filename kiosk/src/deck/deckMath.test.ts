import { describe, expect, it } from "vitest";

import type { PowerDraw, TdpState } from "../../../src/api";
import { faderRange, headline, levelCaption, pushSample, sparkPath, valueAt } from "./deckMath";

const tdp = { limits: { min: 1, default: 6, max: 10, max_ac: 10 }, level_frequencies: { "6": { cpu_khz: [1459200, 2054400, 2227200], gpu_mhz: 475 } } } as unknown as TdpState;

describe("fader", () => {
  it("uses the charger ceiling only on AC", () => {
    const watts = { limits: { min: 5, default: 15, max: 25, max_ac: 30 } } as TdpState;
    expect(faderRange(watts, false)).toEqual({ min: 5, max: 25 });
    expect(faderRange(watts, true)).toEqual({ min: 5, max: 30 });
  });

  it("maps a finger position to a whole value, clamped", () => {
    expect(valueAt(0, 400, 1, 10)).toBe(1);
    expect(valueAt(400, 400, 1, 10)).toBe(10);
    expect(valueAt(0.08 * 400 + 0.46 * 400, 400, 1, 10)).toBe(6);
  });

  it("captions a level with its real top clocks", () => {
    expect(levelCaption(tdp, 6, "es")).toBe("2,2 GHz · 475 MHz");
    expect(levelCaption(tdp, 9, "es")).toBe("");
  });
});

describe("live reading", () => {
  it("prefers FPS, then watts, then temperature", () => {
    expect(headline({ watts: 6, auto: { fps: 58 } } as PowerDraw, 60)).toEqual({ kind: "fps", value: 58 });
    expect(headline({ watts: 6, auto: { fps: null } } as PowerDraw, 60)).toEqual({ kind: "watts", value: 6 });
    expect(headline({ watts: null, auto: { fps: null } } as unknown as PowerDraw, 62)).toEqual({ kind: "temp", value: 62 });
    expect(headline(null, null)).toEqual({ kind: "temp", value: null });
  });

  it("keeps a bounded history and draws it", () => {
    expect(pushSample([1, 2, 3], 4, 3)).toEqual([2, 3, 4]);
    expect(sparkPath([5], 300, 60)).toEqual({ line: "", area: "" });
    const { line, area } = sparkPath([0, 10], 300, 60);
    expect(line).toBe("M0.0,60.0 L300.0,7.8");
    expect(area).toBe("M0.0,60.0 L300.0,7.8 L300,60 L0,60 Z");
  });
});
