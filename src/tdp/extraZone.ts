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
