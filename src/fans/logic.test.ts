import { describe, it, expect } from "vitest";
import { sparklinePath, pushSample, rpmFraction } from "./logic";

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
