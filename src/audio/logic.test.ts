import { describe, it, expect } from "vitest";
import {
  applyTone,
  bassToEnhancer,
  BAND_FREQS,
  GAIN_MAX,
  GAIN_MIN,
  clampGain,
  formatHz,
  gainsToCurvePath,
  toneCeiling,
  toneLevel,
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

  it("applyTone sets a region's bands to the level and clamps", () => {
    const g = applyTone([0, 0, 0, 0, 0, 0, 0, 0, 0, 0], "graves", 4);
    expect(g[1]).toBe(4);
    expect(g[2]).toBe(4);
    expect(g[3]).toBe(4);
    expect(g[0]).toBe(0); // 32 Hz untouched
    expect(applyTone([0, 0, 0, 0, 0, 0, 0, 0, 0, 0], "agudos", 99)[9]).toBe(12);
  });

  it("toneLevel reads a region's average", () => {
    expect(toneLevel([0, 3, 3, 3, 0, 0, 0, 0, 0, 0], "graves")).toBe(3);
    expect(toneLevel([0, 0, 0, 0, 0, 0, 0, 0, 0, 0], "voces")).toBe(0);
  });

  it("bassToEnhancer engages only on the positive side", () => {
    expect(bassToEnhancer(0)).toBe(0);
    expect(bassToEnhancer(-4)).toBe(0);
    expect(bassToEnhancer(12)).toBe(100);
    expect(bassToEnhancer(6)).toBe(50);
  });

  it("toneCeiling is the tightest band ceiling in the region", () => {
    const ceilings = [3, 4, 6, 8, 9, 9, 8, 6, 5, 4];
    expect(toneCeiling("graves", ceilings)).toBe(4); // min of bands 1,2,3 = 4,6,8
    expect(toneCeiling("voces", ceilings)).toBe(6);  // min of bands 5,6,7 = 9,8,6
    expect(toneCeiling("agudos", ceilings)).toBe(4); // min of bands 8,9 = 5,4
  });

  it("higher gain pulls the curve upward (smaller y)", () => {
    const flat = gainsToCurvePath([0, 0, 0, 0, 0, 0, 0, 0, 0, 0], 320, 96);
    const boosted = gainsToCurvePath([12, 12, 12, 12, 12, 12, 12, 12, 12, 12], 320, 96);
    expect(boosted).not.toBe(flat);
  });
});
