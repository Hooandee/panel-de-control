import type { LevelBound } from "../api";
import { clamp } from "../system/logic";

export interface Zone {
  key: "save" | "eco" | "balanced" | "hot" | "turbo";
}

const ZONES: Zone[] = [
  { key: "save" },
  { key: "eco" },
  { key: "balanced" },
  { key: "hot" },
  { key: "turbo" },
];

/** Fill fraction in [0,1] of watts within [min, maxAc]. Clamped. */
export function fraction(watts: number, min: number, maxAc: number): number {
  const span = maxAc - min;
  if (span <= 0) return 0;
  return clamp((watts - min) / span, 0, 1);
}

/** 5 even bands across [0,1] → save eco balanced hot turbo. */
export function zoneFor(frac: number): Zone {
  const clamped = clamp(frac, 0, 1);
  const idx = Math.min(ZONES.length - 1, Math.floor(clamped * ZONES.length));
  return ZONES[idx];
}

/** Arc color: green (hue 140) at 0 → red (hue 8) at 1, passing through amber. */
export function arcColor(frac: number): string {
  const clamped = clamp(frac, 0, 1);
  const hue = Math.round(140 - clamped * 132); // 140 → 8
  return `hsl(${hue}, 75%, 52%)`;
}

/** Margin of a stacked rail above its base, never negative. NaN-safe (→0). */
export function offsetOf(rail: number, base: number): number {
  const v = Math.round(rail - base);
  return Number.isFinite(v) ? Math.max(0, v) : 0;
}

/** Total watts for base + margin, clamped to the rail bound when present. NaN-safe. */
export function totalFor(base: number, offset: number, bound?: LevelBound): number {
  const v = base + Math.max(0, offset);
  if (!Number.isFinite(v)) return Number.isFinite(base) ? base : 0;
  if (!bound) return v;
  return Math.max(bound.min, Math.min(v, bound.max));
}

/** Selectable headroom: max margin that keeps base+margin within the rail. NaN-safe (→0). */
export function maxOffset(base: number, bound?: LevelBound): number {
  if (!bound) return 0;
  const v = bound.max - base;
  return Number.isFinite(v) ? Math.max(0, v) : 0;
}

/**
 * Watt value the learned-band suggestion applies for a battery↔performance *dial*
 * (0 = battery/floor, 1 = performance/ceil). Linear interpolation, rounded, clamped
 * into [floor, ceil]. Mirrors the backend's `target_for_dial` exactly so the applied
 * fixed setpoint matches what the band promises. NaN-safe (→ floor).
 */
export function dialToWatts(floor: number, ceil: number, dial: number): number {
  if (!Number.isFinite(floor) || !Number.isFinite(ceil)) return Number.isFinite(floor) ? floor : 0;
  const lo = Math.min(floor, ceil);
  const hi = Math.max(floor, ceil);
  const d = Math.max(0, Math.min(1, Number.isFinite(dial) ? dial : 0));
  return Math.max(lo, Math.min(hi, Math.round(lo + d * (hi - lo))));
}

/**
 * Extra watts the hardware is drawing ABOVE your set TDP (the "HW boost" the
 * SPPT/FPPT rails deliver on top of PL1). `drawWatts == null` → null (the
 * consumption sensor is unavailable; never fabricate a number). At rest
 * (rounded draw ≤ rounded TDP) → 0. Otherwise → the rounded extra. The UI clamps
 * the boost segment geometrically to the arc, but this magnitude stays exact.
 */
export function boostWatts(tdpWatts: number, drawWatts: number | null): number | null {
  if (drawWatts === null) return null;
  const extra = Math.round(drawWatts) - Math.round(tdpWatts);
  return extra > 0 ? extra : 0;
}

/**
 * Arc fraction [0,1] where the HW-boost segment ends, or `null` when there is no
 * visible segment to draw. Gated by the SAME rounded test as `boostWatts`, then
 * saturates at the scale ceiling if the draw runs past `maxAc` (the ⁺N magnitude
 * stays exact; only the bar saturates). Returns null for a zero-length segment.
 * Note: when the TDP is already at the ceiling the arc is full, so the ⁺N number
 * still reports the overshoot but this returns null — the number and the segment
 * agree everywhere EXCEPT that pinned-at-ceiling case, where there is simply no
 * room left on the arc to draw the extra.
 */
export function boostEndFraction(
  tdpWatts: number,
  drawWatts: number | null,
  min: number,
  maxAc: number,
): number | null {
  const boost = boostWatts(tdpWatts, drawWatts);
  if (boost === null || boost === 0) return null;
  const tdpFrac = fraction(tdpWatts, min, maxAc);
  const end = fraction(Math.min(drawWatts as number, maxAc), min, maxAc);
  return end > tdpFrac ? end : null;
}

