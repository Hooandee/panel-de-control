import { clamp } from "../system/logic";

// A curve point is [temperatureC, pwm] where pwm is the raw 0..255 fan-duty value
// the hardware uses (NOT percent — see pwmToPercent for the display conversion).
export type Point = [number, number];

// Plot geometry: the inner drawing area (width/height in svg px) and the value
// ranges the axes map to. The graph component adds margins around this for labels.
export const GEOM = { width: 280, height: 140, tempMin: 30, tempMax: 100, pwmMax: 255 };
export type Geom = typeof GEOM;

export const pwmToPercent = (pwm: number, max = 255) => Math.round((pwm / max) * 100);
export const percentToPwm = (percent: number, max = 255) => Math.round((percent / 100) * max);

export function curveToPx([temp, pwm]: Point, geom: Geom): { x: number; y: number } {
  const x = ((temp - geom.tempMin) / (geom.tempMax - geom.tempMin)) * geom.width;
  const y = geom.height - (pwm / geom.pwmMax) * geom.height;
  return { x, y };
}

export function pxToCurve(x: number, y: number, geom: Geom): Point {
  const temp = Math.round(geom.tempMin + (x / geom.width) * (geom.tempMax - geom.tempMin));
  const pwm = Math.round((1 - y / geom.height) * geom.pwmMax);
  return [temp, pwm];
}

export function pointsToPath(points: Point[], geom: Geom): string {
  if (!points.length) return "";
  return points
    .map((point, i) => {
      const { x, y } = curveToPx(point, geom);
      return `${i === 0 ? "M" : "L"} ${x} ${y}`;
    })
    .join(" ");
}

/** UI-side mirror of the backend sanitize: non-decreasing temps + pwm, clamped ranges.
 *  Keeps the preview consistent with what the backend will write (the backend still adds
 *  the hot-point safety floor; the next state refresh re-syncs the UI). */
export function clampMonotonic(points: Point[]): Point[] {
  const out: Point[] = [];
  for (const [rawTemp, rawPwm] of points) {
    let temp = clamp(Math.round(rawTemp), 0, 100);
    let pwm = clamp(Math.round(rawPwm), 0, 255);
    if (out.length) {
      temp = Math.max(temp, out[out.length - 1][0]);
      pwm = Math.max(pwm, out[out.length - 1][1]);
    }
    out.push([temp, pwm]);
  }
  return out;
}
