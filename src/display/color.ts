import { ColorPreset } from "../api";

// Quick saturation presets (native first). Values are the integer percent the
// slider/store use (100 = the panel's untouched look).
export const SATURATION_CHIPS = [
  { key: "native", value: 100 },
  { key: "cinema", value: 130 },
  { key: "vivid", value: 150 },
] as const;

export type SaturationChipKey = (typeof SATURATION_CHIPS)[number]["key"];

/** The chip key a saturation value matches exactly, or null (a custom value). */
export function activeSaturationChip(value: number): SaturationChipKey | null {
  return SATURATION_CHIPS.find((c) => c.value === value)?.key ?? null;
}

const NEUTRAL: ColorPreset = { saturation: 100, temperature: 0, contrast: 0 };

/** True when the whole color state is the panel's untouched look. */
export function isNativeColor(p: ColorPreset): boolean {
  return (Object.keys(NEUTRAL) as (keyof ColorPreset)[]).every((k) => p[k] === NEUTRAL[k]);
}

/** True when the CALIBRATION (temperature/contrast — not saturation) deviates from
 *  neutral. Drives the calibration block's "Personalizado" summary + reset. */
export function isCalibrated(p: ColorPreset): boolean {
  return p.temperature !== NEUTRAL.temperature || p.contrast !== NEUTRAL.contrast;
}
