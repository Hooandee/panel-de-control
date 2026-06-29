import { describe, it, expect } from "vitest";
import { fraction, zoneFor, arcColor } from "./logic";
import { offsetOf, totalFor, maxOffset } from "./logic";

describe("fraction", () => {
  it("maps min→0 and maxAc→1", () => {
    expect(fraction(5, 5, 30)).toBe(0);
    expect(fraction(30, 5, 30)).toBe(1);
  });
  it("is ~0.5 at the midpoint", () => {
    expect(fraction(17.5, 5, 30)).toBeCloseTo(0.5, 5);
  });
  it("clamps out-of-range", () => {
    expect(fraction(0, 5, 30)).toBe(0);
    expect(fraction(99, 5, 30)).toBe(1);
  });
  it("handles a degenerate range", () => {
    expect(fraction(10, 10, 10)).toBe(0);
  });
});

describe("zoneFor", () => {
  it("returns the 5 zones across the range", () => {
    expect(zoneFor(0).key).toBe("save");
    expect(zoneFor(0.5).key).toBe("balanced");
    expect(zoneFor(1).key).toBe("turbo");
    expect(zoneFor(0.3).key).toBe("eco");
    expect(zoneFor(0.7).key).toBe("hot");
  });
});

describe("arcColor", () => {
  it("is green-ish at 0 and red-ish at 1", () => {
    expect(arcColor(0)).toMatch(/^hsl\(/);
    // hue high (green ~140) at 0, low (red ~8) at 1
    const hue0 = Number(arcColor(0).match(/hsl\((\d+)/)![1]);
    const hue1 = Number(arcColor(1).match(/hsl\((\d+)/)![1]);
    expect(hue0).toBeGreaterThan(120);
    expect(hue1).toBeLessThan(20);
  });
});

describe("boost margin math", () => {
  it("offsetOf returns the margin, never negative", () => {
    expect(offsetOf(25, 17)).toBe(8);
    expect(offsetOf(15, 20)).toBe(0); // clamped
  });

  it("totalFor adds margin and clamps to the rail bound", () => {
    expect(totalFor(17, 8)).toBe(25); // no bound
    expect(totalFor(35, 20, { min: 5, max: 45 })).toBe(45); // clamped to max
    expect(totalFor(3, 0, { min: 5, max: 45 })).toBe(5); // clamped to min
  });

  it("maxOffset is the headroom up to the rail max", () => {
    expect(maxOffset(17, { min: 5, max: 45 })).toBe(28);
    expect(maxOffset(50, { min: 5, max: 45 })).toBe(0); // base already past max
    expect(maxOffset(17, undefined)).toBe(0);
  });
});
