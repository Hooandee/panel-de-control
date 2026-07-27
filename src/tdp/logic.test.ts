import { describe, it, expect } from "vitest";
import { fraction, zoneFor, arcColor } from "./logic";
import { offsetOf, totalFor, maxOffset, dialToWatts, boostWatts, boostEndFraction, resetWatts } from "./logic";

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

  it("is NaN-safe (never propagates NaN to the UI)", () => {
    expect(offsetOf(NaN, 17)).toBe(0);
    expect(maxOffset(NaN, { min: 5, max: 45 })).toBe(0);
    expect(totalFor(NaN, NaN)).toBe(0);
    expect(totalFor(20, NaN)).toBe(20);
  });
});

describe("dialToWatts (learned-band suggestion)", () => {
  it("lerps battery→floor, performance→ceil, mid→middle (rounded)", () => {
    expect(dialToWatts(15, 21, 0)).toBe(15);
    expect(dialToWatts(15, 21, 1)).toBe(21);
    expect(dialToWatts(15, 21, 0.5)).toBe(18);
    expect(dialToWatts(13, 20, 0.5)).toBe(17); // 16.5 rounds up
  });

  it("clamps the dial and the result into [floor, ceil]", () => {
    expect(dialToWatts(15, 21, -1)).toBe(15);
    expect(dialToWatts(15, 21, 2)).toBe(21);
  });

  it("handles a collapsed band (floor == ceil)", () => {
    expect(dialToWatts(34, 34, 0.5)).toBe(34);
  });

  it("is NaN-safe (→ floor)", () => {
    expect(dialToWatts(15, NaN, 0.5)).toBe(15);
    expect(dialToWatts(15, 21, NaN)).toBe(15);
  });
});

describe("resetWatts (device default reference)", () => {
  it("returns the default when it sits inside the range", () => {
    expect(resetWatts(15, 7, 35)).toBe(15);
  });

  it("clamps a default above the active ceiling (on battery)", () => {
    expect(resetWatts(30, 7, 25)).toBe(25);
  });

  it("clamps a default below the minimum", () => {
    expect(resetWatts(3, 7, 35)).toBe(7);
  });

  it("rounds a fractional default", () => {
    expect(resetWatts(16.6, 7, 35)).toBe(17);
  });

  it("survives a degenerate range (activeMax below min)", () => {
    expect(resetWatts(15, 20, 10)).toBe(20);
  });

  it("is NaN-safe (→ min)", () => {
    expect(resetWatts(NaN, 7, 35)).toBe(7);
  });

  it("never returns NaN when a limit is NaN", () => {
    expect(resetWatts(15, NaN, 35)).toBe(15);
    expect(resetWatts(15, 7, NaN)).toBe(7);
    expect(Number.isFinite(resetWatts(NaN, NaN, NaN))).toBe(true);
  });
});

describe("boostWatts (HW boost above your TDP)", () => {
  it("returns null when the draw sensor is unavailable", () => {
    expect(boostWatts(22, null)).toBeNull();
  });

  it("returns 0 at rest (draw <= tdp)", () => {
    expect(boostWatts(22, 22)).toBe(0);
    expect(boostWatts(22, 20)).toBe(0);
  });

  it("returns the extra watts when the chip boosts above your TDP", () => {
    expect(boostWatts(22, 31)).toBe(9);
  });

  it("rounds both sides before subtracting", () => {
    expect(boostWatts(22.4, 30.6)).toBe(9); // round(31) - round(22) = 9
    expect(boostWatts(21.6, 22.4)).toBe(0); // round(22) == round(22) → rest
  });

  it("still reports the real extra when draw exceeds max_ac (clamp is UI-only)", () => {
    expect(boostWatts(33, 38)).toBe(5);
  });
});

describe("boostEndFraction (arc geometry of the boost segment)", () => {
  // range [7, 35]
  it("returns null when the draw sensor is unavailable", () => {
    expect(boostEndFraction(22, null, 7, 35)).toBeNull();
  });

  it("returns null at rest (gated by the same rounded test as boostWatts)", () => {
    expect(boostEndFraction(22, 22, 7, 35)).toBeNull();
    expect(boostEndFraction(22, 20, 7, 35)).toBeNull();
  });

  it("returns the draw fraction for a real boost", () => {
    // draw 31 within [7,35] → (31-7)/28
    expect(boostEndFraction(22, 31, 7, 35)).toBeCloseTo(24 / 28, 5);
  });

  it("saturates at the ceiling (1.0) when draw exceeds max_ac", () => {
    // tdp 30, draw 38 > 35 → clamp to 35 → fraction 1.0
    expect(boostEndFraction(30, 38, 7, 35)).toBe(1);
  });

  it("returns null when the segment would be zero-length (TDP already at ceiling)", () => {
    // tdp 35 (=max_ac, frac 1.0), draw 38 → end clamps to 1.0 == tdpFrac → no segment
    expect(boostEndFraction(35, 38, 7, 35)).toBeNull();
  });
});
