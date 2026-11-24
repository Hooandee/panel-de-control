// "low"/"high": a manual request outside the safe range, which the firmware may refuse.
export type ExtraZone = "low" | "high" | null;

export function extraZone(requested: number, safeMin: number, safeMax: number): ExtraZone {
  if (requested < safeMin) return "low";
  if (requested > safeMax) return "high";
  return null;
}

export function manualCeiling(safeMax: number, onAc: boolean, manualMaxAc?: number): number {
  return onAc && manualMaxAc !== undefined ? Math.max(safeMax, manualMaxAc) : safeMax;
}

export interface WattsRange {
  requestMin: number;
  activeMax: number;
  sliderMax: number;
}

/** Slider bounds for the sustained limit: never more than the current power source can deliver. */
export function wattsRange(
  tdp: { limits: { min: number; max: number; max_ac: number }; request_min?: number; on_ac: boolean; manual_max_ac?: number },
): WattsRange {
  const activeMax = tdp.on_ac ? tdp.limits.max_ac : tdp.limits.max;
  return {
    requestMin: tdp.request_min ?? tdp.limits.min,
    activeMax,
    sliderMax: manualCeiling(activeMax, tdp.on_ac, tdp.manual_max_ac),
  };
}
