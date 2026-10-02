// Where a manual TDP request sits relative to the range Panel de Control stands behind.
// "low" and "high" are requests the firmware may refuse or clamp.
export type ExtraZone = "low" | "high" | null;

export function extraZone(requested: number, safeMin: number, safeMax: number): ExtraZone {
  if (requested < safeMin) return "low";
  if (requested > safeMax) return "high";
  return null;
}

// Ceiling of the manual slider: the charger extra range when present, else the safe one.
export function manualCeiling(safeMax: number, onAc: boolean, manualMaxAc?: number): number {
  return onAc && manualMaxAc !== undefined ? Math.max(safeMax, manualMaxAc) : safeMax;
}
