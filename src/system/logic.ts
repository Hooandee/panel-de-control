// Pure scale conversion for system controls (brightness, volume).
// SteamClient works in a 0..1 fraction; the UI works in an integer percent.

export const clamp = (v: number, lo: number, hi: number): number =>
  Math.min(hi, Math.max(lo, v));

/** 0..1 fraction → integer percent (0..100), clamped. */
export function toPercent(fraction: number): number {
  return Math.round(clamp(fraction, 0, 1) * 100);
}

/** integer percent (0..100) → 0..1 fraction, clamped. */
export function fromPercent(percent: number): number {
  return clamp(percent, 0, 100) / 100;
}
