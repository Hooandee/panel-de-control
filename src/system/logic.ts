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

/**
 * Decide whether an incoming hardware echo should update the slider while a set
 * is pending. A slider writes optimistically on every drag tick and the hardware
 * echoes each applied value back asynchronously; a late echo for an EARLIER drag
 * position would yank the slider backward ("jumps"). Accept when: nothing is
 * pending (live tracking), the echo confirms the pending value (hardware caught
 * up), or the wait exceeded `timeoutMs` (hardware clamped/settled elsewhere).
 */
export function acceptEcho(
  pending: number | null,
  echo: number,
  msSinceSet: number,
  timeoutMs = 600,
): boolean {
  if (pending === null) return true;
  if (echo === pending) return true;
  return msSinceSet > timeoutMs;
}
