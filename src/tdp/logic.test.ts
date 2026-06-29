import { describe, it, expect } from "vitest";
import { fraction, zoneFor, arcColor, angleFor } from "./logic";

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

describe("angleFor", () => {
  it("maps fraction across the sweep", () => {
    expect(angleFor(0, 240)).toBe(0);
    expect(angleFor(1, 240)).toBe(240);
    expect(angleFor(0.5, 240)).toBe(120);
  });
});
