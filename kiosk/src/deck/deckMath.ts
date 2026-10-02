import type { PowerDraw, TdpState } from "../../../src/api";

export function faderRange(tdp: TdpState | null, onAc: boolean): { min: number; max: number } {
  if (!tdp?.limits) return { min: 0, max: 1 };
  const max = onAc ? Math.max(tdp.limits.max, tdp.limits.max_ac) : tdp.limits.max;
  return { min: tdp.limits.min, max: Math.max(tdp.limits.min + 1, max) };
}

/** Value under a finger `fromBottom` px above the fader's bottom edge (the first 8% is the floor). */
export function valueAt(fromBottom: number, height: number, min: number, max: number): number {
  const fraction = height > 0 ? (fromBottom / height - 0.08) / 0.92 : 0;
  const clamped = Math.max(0, Math.min(1, fraction));
  return Math.round(min + clamped * (max - min));
}

export function levelCaption(tdp: TdpState | null, level: number | null, lang: string): string {
  const freq = level != null ? tdp?.level_frequencies?.[String(level)] : undefined;
  if (!freq) return "";
  const ghz = Math.max(...freq.cpu_khz) / 1e6;
  const cpu = ghz.toLocaleString(lang, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  return `${cpu} GHz · ${freq.gpu_mhz} MHz`;
}

export function fpsOrWatts(power: PowerDraw | null): { kind: "fps" | "watts"; value: number | null } {
  const fps = power?.auto?.fps;
  if (fps != null) return { kind: "fps", value: fps };
  return { kind: "watts", value: power?.watts ?? null };
}

export function pushSample(samples: readonly number[], value: number, keep: number): number[] {
  return [...samples, value].slice(-keep);
}

/** Line (and closed area) for a history, scaled from zero so small wobbles stay small. */
export function sparkPath(samples: readonly number[], width: number, height: number): { line: string; area: string } {
  if (samples.length < 2) return { line: "", area: "" };
  const high = Math.max(...samples) * 1.15 || 1;
  const step = width / (samples.length - 1);
  const y = (v: number) => height - (v / high) * height;
  const line = samples.map((v, i) => `${i === 0 ? "M" : "L"}${(i * step).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  return { line, area: `${line} L${width},${height} L0,${height} Z` };
}
