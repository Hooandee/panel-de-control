import { clamp } from "../system/logic";

// A graphic EQ: 10 fixed bands, each a gain in dB. Mirrors py_modules/audio/const.py.
export const BAND_FREQS = [32, 64, 125, 250, 500, 1000, 2000, 4000, 8000, 16000];
export const GAIN_MIN = -12;
export const GAIN_MAX = 12;

export const clampGain = (g: number): number => clamp(g, GAIN_MIN, GAIN_MAX);

/** Negative headroom so a boosted band never clips: -(highest positive gain). */
export function computePreamp(gains: number[]): number {
  const peak = Math.max(0, ...gains.map(clampGain));
  return peak > 0 ? -peak : 0;
}

export function formatHz(freq: number): string {
  return freq >= 1000 ? `${freq / 1000}k` : `${freq}`;
}

/**
 * Smooth SVG path (Catmull-Rom → cubic Bézier) of the EQ response across the panel
 * width. Band i sits at x = i/(n-1)·width; gain maps around the vertical centre, +gain
 * pulling the line up (smaller y). Purely presentational.
 */
export function gainsToCurvePath(gains: number[], width: number, height: number): string {
  const n = gains.length;
  const mid = height / 2;
  const span = (height / 2) * 0.85; // keep the extremes inside the canvas
  const pts = gains.map((g, i) => ({
    x: (i / (n - 1)) * width,
    y: mid - (clampGain(g) / GAIN_MAX) * span,
  }));

  let d = `M ${pts[0].x.toFixed(1)} ${pts[0].y.toFixed(1)}`;
  for (let i = 0; i < n - 1; i++) {
    const p0 = pts[i === 0 ? 0 : i - 1];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[i + 2 < n ? i + 2 : n - 1];
    const c1x = p1.x + (p2.x - p0.x) / 6;
    const c1y = p1.y + (p2.y - p0.y) / 6;
    const c2x = p2.x - (p3.x - p1.x) / 6;
    const c2y = p2.y - (p3.y - p1.y) / 6;
    d += ` C ${c1x.toFixed(1)} ${c1y.toFixed(1)} ${c2x.toFixed(1)} ${c2y.toFixed(1)} ${p2.x.toFixed(1)} ${p2.y.toFixed(1)}`;
  }
  return d;
}
