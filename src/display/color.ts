import type { ColorPreset, Calibration } from "../api";

export const NEUTRAL: ColorPreset = {
  saturation: 100, temperature: 0, contrast: 0, gamma: 0, hue: 0, black: 0,
  gain_r: 100, gain_g: 100, gain_b: 100, vibrance: 0,
};

// Every field but saturation, derived from NEUTRAL so it can't drift. Kept out of
// api.ts so this pure module avoids the @decky/api runtime import.
export const CALIBRATION_KEYS = (Object.keys(NEUTRAL) as (keyof ColorPreset)[])
  .filter((k) => k !== "saturation") as (keyof Calibration)[];

/** True when the whole color state is the panel's untouched look. */
export function isNativeColor(p: ColorPreset): boolean {
  return p.saturation === NEUTRAL.saturation && !isCalibrated(p);
}

/** True when any CALIBRATION field (everything but the per-game saturation) deviates
 *  from neutral. Drives the "Avanzado" block's "Personalizado" summary + reset. */
export function isCalibrated(p: ColorPreset): boolean {
  return CALIBRATION_KEYS.some((k) => p[k] !== NEUTRAL[k]);
}

/** The calibration subset of a preset — what preview/set_calibration send. */
export function pickCalibration(p: ColorPreset): Calibration {
  const out = {} as Calibration;
  for (const k of CALIBRATION_KEYS) out[k] = p[k];
  return out;
}
