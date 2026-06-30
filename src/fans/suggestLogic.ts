import { clamp } from "../system/logic";
import type { Point } from "./curve";

// The three anchor curves share the same temp anchors; the dial blends their pwm.
// dial ∈ [-1, 1]: -1 = quiet, 0 = balanced, +1 = cool.
function lerpCurves(a: Point[], b: Point[], t: number): Point[] {
  return a.map(([temp, pwmA], i) => {
    const pwmB = b[i]?.[1] ?? pwmA;
    return [temp, Math.round(pwmA + (pwmB - pwmA) * t)] as Point;
  });
}

/** Blend quiet↔balanced↔cool by a single silence↔cool dial. */
export function interpolateCurves(
  quiet: Point[],
  balanced: Point[],
  cool: Point[],
  dial: number,
): Point[] {
  const d = clamp(dial, -1, 1);
  if (d < 0) return lerpCurves(balanced, quiet, -d);
  if (d > 0) return lerpCurves(balanced, cool, d);
  return balanced.map(([t, p]) => [t, p] as Point);
}
