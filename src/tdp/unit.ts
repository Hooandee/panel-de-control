export type PowerUnit = "W" | "level";

export interface LevelFrequencies {
  cpu_khz: number[];
  gpu_mhz: number | null;
}

export const isLevelUnit = (unit: string | null | undefined): boolean => unit === "level";

const ghz = (khz: number): string => (khz / 1_000_000).toFixed(1);

export function levelFrequencySummary(entry: LevelFrequencies | null | undefined): string | null {
  if (!entry || entry.cpu_khz.length === 0) return null;
  const cpu = `CPU ${entry.cpu_khz.map(ghz).join(" · ")} GHz`;
  return entry.gpu_mhz === null ? cpu : `${cpu}  ·  GPU ${entry.gpu_mhz} MHz`;
}
