import { describe, it, expect } from "vitest";
import { toPercent, fromPercent } from "./logic";

// SteamClient reports brightness/volume as a 0..1 fraction; the UI shows an
// integer percent and lets the user pick an exact value. These convert between
// the two and clamp defensively.

describe("toPercent", () => {
  it("maps 0→0 and 1→100", () => {
    expect(toPercent(0)).toBe(0);
    expect(toPercent(1)).toBe(100);
  });
  it("rounds to the nearest integer percent", () => {
    expect(toPercent(0.5)).toBe(50);
    expect(toPercent(0.244)).toBe(24);
    expect(toPercent(0.246)).toBe(25);
  });
  it("clamps out-of-range fractions", () => {
    expect(toPercent(-0.2)).toBe(0);
    expect(toPercent(1.5)).toBe(100);
  });
});

describe("fromPercent", () => {
  it("maps 0→0 and 100→1", () => {
    expect(fromPercent(0)).toBe(0);
    expect(fromPercent(100)).toBe(1);
  });
  it("maps 50→0.5", () => {
    expect(fromPercent(50)).toBe(0.5);
  });
  it("clamps out-of-range percents", () => {
    expect(fromPercent(-10)).toBe(0);
    expect(fromPercent(150)).toBe(1);
  });
});
