import { describe, it, expect } from "vitest";
import { pwmToPercent, percentToPwm, pointsToPath, curveToPx, pxToCurve, clampMonotonic, curveValueAt, GEOM } from "./curve";

const geom = { ...GEOM, width: 280, height: 140 };

describe("pwm <-> percent", () => {
  it("round-trips at the ends", () => {
    expect(pwmToPercent(0)).toBe(0);
    expect(pwmToPercent(255)).toBe(100);
    expect(percentToPwm(100)).toBe(255);
    expect(percentToPwm(0)).toBe(0);
  });
});

describe("curveToPx / pxToCurve", () => {
  it("maps temp domain to x and full pwm to the top (y=0)", () => {
    const { x, y } = curveToPx([geom.tempMin, 255], geom);
    expect(x).toBe(0);
    expect(y).toBe(0);
  });
  it("round-trips within rounding tolerance", () => {
    const { x, y } = curveToPx([70, 128], geom);
    const [temp, pwm] = pxToCurve(x, y, geom);
    expect(Math.abs(temp - 70)).toBeLessThanOrEqual(1);
    expect(Math.abs(pwm - 128)).toBeLessThanOrEqual(2);
  });
});

describe("pointsToPath", () => {
  it("returns an M..L path through the points", () => {
    const d = pointsToPath([[geom.tempMin, 0], [geom.tempMax, 255]], geom);
    expect(d).toBe(`M 0 ${geom.height} L ${geom.width} 0`);
  });
  it("returns empty for no points", () => {
    expect(pointsToPath([], geom)).toBe("");
  });
});

describe("clampMonotonic", () => {
  it("forces non-decreasing temps and pwm + clamps ranges", () => {
    const out = clampMonotonic([[60, 200], [50, 100], [120, 999]]);
    expect(out).toEqual([[60, 200], [60, 200], [100, 255]]);
  });
});

describe("curveValueAt", () => {
  const pts: [number, number][] = [
    [50, 40 * 2.55],
    [60, 49 * 2.55],
    [70, 58 * 2.55],
    [80, 67 * 2.55],
    [88, 75 * 2.55],
  ];
  it("clamps below the first point", () => {
    expect(curveValueAt(pts, 30)).toBe(pts[0][1]);
  });
  it("clamps above the last point", () => {
    expect(curveValueAt(pts, 120)).toBe(pts[pts.length - 1][1]);
  });
  it("returns the exact value at a knot", () => {
    expect(curveValueAt(pts, 70)).toBe(58 * 2.55);
  });
  it("interpolates linearly between knots", () => {
    // midpoint of [60→49%, 70→58%] at 65° = 53.5%
    expect(curveValueAt(pts, 65)).toBeCloseTo(53.5 * 2.55, 5);
  });
  it("returns 0 for an empty curve", () => {
    expect(curveValueAt([], 60)).toBe(0);
  });
});
