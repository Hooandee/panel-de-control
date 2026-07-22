import { describe, it, expect } from "vitest";
import { sparklinePath, pushSample, rpmFraction, presetConverges, isSolo, tempsAvailable } from "./logic";
import type { FanState } from "../api";

const fanState = (fans: number, temps: number): FanState =>
  ({
    supported: true,
    fans: Array.from({ length: fans }, (_, i) => ({ label: `fan${i}`, rpm: 1000, percent: null })),
    temps: Array.from({ length: temps }, (_, i) => ({ label: `t${i}`, celsius: 50 })),
    source: "hwmon",
  } as unknown as FanState);

describe("isSolo / tempsAvailable", () => {
  it("solo = exactly one fan and one temp", () => {
    expect(isSolo(fanState(1, 1))).toBe(true);
    expect(isSolo(fanState(2, 1))).toBe(false);
    expect(isSolo(fanState(1, 2))).toBe(false);
  });
  it("temps block is available only with temps and not in the solo case", () => {
    expect(tempsAvailable(fanState(2, 2))).toBe(true); // multi → separate temps block
    expect(tempsAvailable(fanState(1, 1))).toBe(false); // solo → temp merged into fan card
    expect(tempsAvailable(fanState(2, 0))).toBe(false); // no temps
    expect(tempsAvailable(null)).toBe(false); // not loaded yet
  });
});

describe("presetConverges", () => {
  // On these devices the fan sits at a physical floor when cool, so silent/
  // balanced/performance all look identical until temps climb into the zone
  // where their curves diverge. The hint tells the user that's expected — not
  // that the preset failed. Only for the three fixed presets; never for
  // auto/custom/adaptive (they aren't "presets look the same" cases).
  it("is true for a fixed preset while cool (below the divergence temp)", () => {
    expect(presetConverges("silent", 40)).toBe(true);
    expect(presetConverges("balanced", 55)).toBe(true);
    expect(presetConverges("performance", 30)).toBe(true);
  });
  it("is false once temps reach the divergence zone", () => {
    expect(presetConverges("silent", 65)).toBe(false);
    expect(presetConverges("performance", 80)).toBe(false);
  });
  it("is false for non-fixed modes regardless of temp", () => {
    expect(presetConverges("auto", 40)).toBe(false);
    expect(presetConverges("custom", 40)).toBe(false);
    expect(presetConverges("adaptive", 40)).toBe(false);
  });
  it("is false when live temp is unknown (no marker to reason about)", () => {
    expect(presetConverges("silent", null)).toBe(false);
  });
});

describe("pushSample", () => {
  it("appends within capacity", () => {
    expect(pushSample([1, 2], 3, 3)).toEqual([1, 2, 3]);
  });
  it("drops the oldest when over capacity", () => {
    expect(pushSample([1, 2, 3], 4, 3)).toEqual([2, 3, 4]);
  });
  it("starts from empty", () => {
    expect(pushSample([], 5, 3)).toEqual([5]);
  });
  it("does not mutate the input array", () => {
    const b = [1, 2, 3];
    pushSample(b, 4, 3);
    expect(b).toEqual([1, 2, 3]);
  });
});

describe("sparklinePath", () => {
  it("returns an empty string for no data", () => {
    expect(sparklinePath([], 100, 20)).toBe("");
  });
  it("maps max to the top (y=0) and min to the bottom (y=height)", () => {
    expect(sparklinePath([0, 10], 100, 20)).toBe("M 0 20 L 100 0");
  });
  it("draws a flat mid line when all values are equal", () => {
    expect(sparklinePath([5, 5, 5], 100, 20)).toBe("M 0 10 L 50 10 L 100 10");
  });
});

describe("rpmFraction", () => {
  it("is rpm over the nominal max when nothing faster was seen", () => {
    expect(rpmFraction(3500, 0, 7000)).toBeCloseTo(0.5);
  });
  it("clamps to 1 when rpm exceeds the denominator", () => {
    expect(rpmFraction(9000, 0, 7000)).toBe(1);
  });
  it("calibrates to the observed peak when it exceeds nominal", () => {
    expect(rpmFraction(4500, 9000, 7000)).toBeCloseTo(0.5);
  });
  it("is 0 at rest", () => {
    expect(rpmFraction(0, 0, 7000)).toBe(0);
  });
});
