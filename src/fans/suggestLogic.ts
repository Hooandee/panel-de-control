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

export type SuggestStateKind =
  | "ready"       // enough data → curve + dial + apply
  | "learning"    // some data, more time needed → progress + green preview
  | "spread"      // enough time but too little temperature variation
  | "empty"       // no usable data yet (or an error) → "start playing"
  | "no_game"     // no running game to learn from
  | "disabled"    // telemetry opted out
  | "unsupported"; // device can't write fan curves

// While still learning the bar must NEVER read full (never-fake) — cap just under 1
// so a 29.5-min dwell (which round(minutes) would show as the 30-min target) can't
// look "done" while the honest gate is still `too_few`.
const _LEARNING_MAX = 0.99;

/**
 * Fraction (0..1) toward the learning target, derived from raw SECONDS so it stays
 * honest at the round-up boundary. 0 for a non-positive target.
 *
 * `available` = the backend's honest "enough data" verdict. Until it flips true the
 * bar is capped below 1 (still learning); once true it reads a full 1.
 */
export function learningProgress(seconds: number, targetSeconds: number, available: boolean): number {
  if (available) return 1;
  if (targetSeconds <= 0) return 0;
  return clamp(seconds / targetSeconds, 0, _LEARNING_MAX);
}

/**
 * Whole minutes still to go before unlocking, rounded UP with a floor of 1 so the
 * card never says "~0 min" while the state is still `learning` (never-fake). Only
 * meaningful while learning; once available the card no longer shows it.
 */
export function minutesLeft(seconds: number, targetSeconds: number): number {
  return Math.max(1, Math.ceil((targetSeconds - seconds) / 60));
}

/** Map a suggestion (available + honest reason) to the card's display state. */
export function suggestState(s: { available: boolean; reason: string }): SuggestStateKind {
  if (s.available) return "ready";
  switch (s.reason) {
    case "disabled": return "disabled";
    case "unsupported": return "unsupported";
    case "no_game": return "no_game";
    case "flat": return "spread";
    case "too_few": return "learning";
    default: return "empty"; // no_data | error
  }
}

// A2 — thermal clarity: classify a temperature into a meaning a non-expert reads.
// Thresholds tuned for handheld APUs (Steam Deck / Ally / Legion / Claw): these
// chips run happily into the 70s and throttle near ~95 °C, so "hot" starts at 75
// (near the HW safety floor of 76) and "limit" at 88 (getting close to TjMax).
export type ThermalZone = "cool" | "warm" | "hot" | "limit";

// The zone boundaries in °C — the SINGLE source of truth. `thermalZone` (meaning)
// and ThermalScale's colored segments (visual) both derive from these so the bar
// and the classification can never drift apart.
export const THERMAL_BOUNDS = { warm: 60, hot: 75, limit: 88 } as const;

export function thermalZone(tempC: number): ThermalZone {
  if (tempC < THERMAL_BOUNDS.warm) return "cool";
  if (tempC < THERMAL_BOUNDS.hot) return "warm";
  if (tempC < THERMAL_BOUNDS.limit) return "hot";
  return "limit";
}

// A3 — translate the silence↔cool dial (-100..100) into a plain-language tone.
export type DialTone = "quiet" | "balanced" | "cool";

export function dialTone(dial: number): DialTone {
  if (dial <= -33) return "quiet";
  if (dial >= 33) return "cool";
  return "balanced";
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
