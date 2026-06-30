import { describe, expect, it } from "vitest";
import type { Point } from "./curve";
import { interpolateCurves } from "./suggestLogic";

const QUIET: Point[] = [[40, 0], [50, 0], [60, 20], [70, 60], [80, 120], [85, 160], [90, 200], [95, 230]];
const BAL: Point[] = [[40, 0], [50, 20], [60, 50], [70, 100], [80, 150], [85, 190], [90, 220], [95, 245]];
const COOL: Point[] = [[40, 30], [50, 60], [60, 90], [70, 150], [80, 190], [85, 220], [90, 240], [95, 255]];

describe("interpolateCurves", () => {
  it("returns balanced at dial 0", () => {
    expect(interpolateCurves(QUIET, BAL, COOL, 0)).toEqual(BAL);
  });

  it("returns quiet at dial -1 and cool at dial +1", () => {
    expect(interpolateCurves(QUIET, BAL, COOL, -1)).toEqual(QUIET);
    expect(interpolateCurves(QUIET, BAL, COOL, 1)).toEqual(COOL);
  });

  it("clamps the dial beyond [-1, 1]", () => {
    expect(interpolateCurves(QUIET, BAL, COOL, -5)).toEqual(QUIET);
    expect(interpolateCurves(QUIET, BAL, COOL, 5)).toEqual(COOL);
  });

  it("interpolates pwm halfway between balanced and cool at dial 0.5", () => {
    const out = interpolateCurves(QUIET, BAL, COOL, 0.5);
    // temps preserved
    expect(out.map(([t]) => t)).toEqual(BAL.map(([t]) => t));
    // each pwm is the rounded midpoint of balanced and cool
    out.forEach(([, pwm], i) => {
      expect(pwm).toBe(Math.round((BAL[i][1] + COOL[i][1]) / 2));
    });
  });

  it("interpolates between quiet and balanced for negative dial", () => {
    const out = interpolateCurves(QUIET, BAL, COOL, -0.5);
    out.forEach(([, pwm], i) => {
      expect(pwm).toBe(Math.round((QUIET[i][1] + BAL[i][1]) / 2));
    });
  });
});
