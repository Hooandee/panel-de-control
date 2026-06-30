import type { LevelBound } from "../api";

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
  return Math.max(0, Math.min(1, (watts - min) / span));
}

/** 5 even bands across [0,1] → save eco balanced hot turbo. */
export function zoneFor(frac: number): Zone {
  const clamped = Math.max(0, Math.min(1, frac));
  const idx = Math.min(ZONES.length - 1, Math.floor(clamped * ZONES.length));
  return ZONES[idx];
}

/** Arc color: green (hue 140) at 0 → red (hue 8) at 1, passing through amber. */
export function arcColor(frac: number): string {
  const clamped = Math.max(0, Math.min(1, frac));
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

