export type PowerUnit = "W" | "level";

export interface LevelFrequencies {
  cpu_khz: number[];
  gpu_mhz: number | null;
}

export const isLevelUnit = (unit: string | null | undefined): boolean => unit === "level";

const ghz = (khz: number): string => (khz / 1_000_000).toFixed(1);

export function levelFrequencySummary(
  entry: LevelFrequencies | null | undefined,
  gpuEntry: LevelFrequencies | null | undefined = entry,
  gpuFirst = false,
): string | null {
  if (!entry || entry.cpu_khz.length === 0) return null;
  const cpu = `CPU ${entry.cpu_khz.map(ghz).join(" · ")} GHz`;
  const gpuMhz = gpuEntry?.gpu_mhz ?? null;
  if (gpuMhz === null) return cpu;
  const gpu = `GPU ${gpuMhz} MHz`;
  return gpuFirst ? `${gpu}  ·  ${cpu}` : `${cpu}  ·  ${gpu}`;
}
