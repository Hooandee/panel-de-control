import { describe, expect, it } from "vitest";
import type { Point } from "./curve";
import { dialTone, interpolateCurves, learningProgress, minutesLeft, suggestState, thermalZone } from "./suggestLogic";

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

describe("learningProgress", () => {
  const TARGET = 1800; // 30 min in seconds

  it("is 0 with no elapsed time", () => {
    expect(learningProgress(0, TARGET, false)).toBe(0);
  });
  it("is the fraction part-way", () => {
    expect(learningProgress(720, TARGET, false)).toBeCloseTo(0.4); // 12 min
  });
  it("is 0 for a non-positive target (avoid divide-by-zero)", () => {
    expect(learningProgress(600, 0, false)).toBe(0);
  });

  // never-fake: while still learning (not available) the bar must NEVER read full,
  // even at the round-up boundary where minutes(round) would show the target.
  it("never reaches 1 while learning, even at 1770/1799 s (round→30 min)", () => {
    expect(learningProgress(1770, TARGET, false)).toBeLessThan(1);
    expect(learningProgress(1799, TARGET, false)).toBeLessThan(1);
    // …and at/over target-while-learning (shouldn't happen, but be safe) still < 1.
    expect(learningProgress(1800, TARGET, false)).toBeLessThan(1);
    expect(learningProgress(9999, TARGET, false)).toBeLessThan(1);
  });

  it("is exactly 1 once available (enough data)", () => {
    expect(learningProgress(1800, TARGET, true)).toBe(1);
    expect(learningProgress(1200, TARGET, true)).toBe(1);
  });
});

describe("minutesLeft", () => {
  const TARGET = 1800; // 30 min in seconds

  it("rounds the remaining time UP so it never shows 0 while learning", () => {
    // 1770 s = 29.5 min elapsed → 30 s left → ceil → 1 min (never "0 min").
    expect(minutesLeft(1770, TARGET)).toBe(1);
    // 1799 s → 1 s left → ceil → 1 min.
    expect(minutesLeft(1799, TARGET)).toBe(1);
  });
  it("has a floor of 1 minute (never 0) even when elapsed >= target", () => {
    expect(minutesLeft(1800, TARGET)).toBe(1);
    expect(minutesLeft(9999, TARGET)).toBe(1);
  });
  it("reports whole minutes remaining part-way", () => {
    expect(minutesLeft(600, TARGET)).toBe(20); // 10 min in → 20 left
    expect(minutesLeft(0, TARGET)).toBe(30);
  });
});

describe("suggestState", () => {
  const s = (over: Partial<{ available: boolean; reason: string }>) =>
    ({ available: false, reason: "ok", minutes: 0, target_minutes: 30, band: null, curves: null, ...over });

  it("ready when available", () => {
    expect(suggestState(s({ available: true, reason: "ok" }))).toBe("ready");
  });
  it("maps each unavailable reason to its state", () => {
    expect(suggestState(s({ reason: "too_few" }))).toBe("learning");
    expect(suggestState(s({ reason: "flat" }))).toBe("spread");
    expect(suggestState(s({ reason: "no_data" }))).toBe("empty");
    expect(suggestState(s({ reason: "no_game" }))).toBe("no_game");
    expect(suggestState(s({ reason: "disabled" }))).toBe("disabled");
    expect(suggestState(s({ reason: "unsupported" }))).toBe("unsupported");
    expect(suggestState(s({ reason: "error" }))).toBe("empty");
  });
});

describe("thermalZone", () => {
  it("classifies handheld-APU temperature bands", () => {
    expect(thermalZone(45)).toBe("cool");
    expect(thermalZone(59.9)).toBe("cool");
    expect(thermalZone(60)).toBe("warm");
    expect(thermalZone(74)).toBe("warm");
    expect(thermalZone(75)).toBe("hot");
    expect(thermalZone(87)).toBe("hot");
    expect(thermalZone(88)).toBe("limit");
    expect(thermalZone(97)).toBe("limit");
  });
  it("is monotonic across the boundaries (never skips a zone)", () => {
    const order = ["cool", "warm", "hot", "limit"];
    let last = -1;
    for (let t = 30; t <= 100; t++) {
      const idx = order.indexOf(thermalZone(t));
      expect(idx).toBeGreaterThanOrEqual(last);
      last = idx;
    }
  });
});

describe("dialTone", () => {
  it("maps the silence↔cool dial (-100..100) to a plain-language tone", () => {
    expect(dialTone(-100)).toBe("quiet");
    expect(dialTone(-33)).toBe("quiet");
    expect(dialTone(-32)).toBe("balanced");
    expect(dialTone(0)).toBe("balanced");
    expect(dialTone(32)).toBe("balanced");
    expect(dialTone(33)).toBe("cool");
    expect(dialTone(100)).toBe("cool");
  });
});
