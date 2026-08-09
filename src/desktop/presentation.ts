export interface VramView {
  value: string;
  total: string;
  fraction: number;
}

export function dialFraction(
  value: number | null,
  min: number | null,
  max: number | null,
): number {
  if (value == null || min == null || max == null || max <= min) return 0;
  return Math.max(0, Math.min(1, (value - min) / (max - min)));
}

export function clockText(
  mhz: number | null,
  idle: string,
  unavailable: string,
): string {
  if (mhz == null) return unavailable;
  if (mhz <= 0) return idle;
  return `${Math.round(mhz)} MHz`;
}

export function metricText(
  value: number | null,
  unit: string,
  unavailable: string,
): string {
  if (value == null) return unavailable;
  return `${Number.isInteger(value) ? value : value.toFixed(1)} ${unit}`;
}

export function vramView(
  usedMb: number | null,
  totalMb: number | null,
  unavailable: string,
): VramView {
  if (usedMb == null || totalMb == null || totalMb <= 0) {
    return { value: unavailable, total: "", fraction: 0 };
  }
  return {
    value: (usedMb / 1024).toFixed(1),
    total: `${(totalMb / 1024).toFixed(1)} GB`,
    fraction: Math.max(0, Math.min(1, usedMb / totalMb)),
  };
}
