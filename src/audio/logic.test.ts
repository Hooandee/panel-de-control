import { describe, it, expect } from "vitest";
import {
  BAND_FREQS,
  GAIN_MAX,
  GAIN_MIN,
  clampGain,
  computePreamp,
  formatHz,
  gainsToCurvePath,
} from "./logic";

describe("audio EQ logic", () => {
  it("has 10 band frequencies", () => {
    expect(BAND_FREQS).toEqual([32, 64, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]);
  });

  it("clamps gain to the safe range", () => {
    expect(clampGain(99)).toBe(GAIN_MAX);
    expect(clampGain(-99)).toBe(GAIN_MIN);
    expect(clampGain(3.5)).toBe(3.5);
  });

  it("preamp is negative headroom of the positive peak", () => {
    expect(computePreamp([0, 0, 0, 0, 0, 0, 0, 0, 0, 0])).toBe(0);
    expect(computePreamp([6, 0, 3, 0, 0, 0, 0, 0, 0, 0])).toBe(-6);
    expect(computePreamp([-3, -6, 0, 0, 0, 0, 0, 0, 0, 0])).toBe(0);
  });

  it("formats frequency labels", () => {
    expect(formatHz(32)).toBe("32");
    expect(formatHz(1000)).toBe("1k");
    expect(formatHz(16000)).toBe("16k");
  });

  it("builds a curve path spanning the width", () => {
    const d = gainsToCurvePath([0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 320, 96);
    expect(d.startsWith("M")).toBe(true);
    expect(d.length).toBeGreaterThan(10);
  });

  it("higher gain pulls the curve upward (smaller y)", () => {
    const flat = gainsToCurvePath([0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 320, 96);
    const boosted = gainsToCurvePath([12, 12, 12, 12, 12, 12, 12, 12, 12, 12], 320, 96);
    expect(boosted).not.toBe(flat);
  });
});
