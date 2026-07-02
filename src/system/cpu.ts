// Pure helpers for the CPU card. No React/SteamClient so they're unit-testable.
import { clamp } from "./logic";

/** kHz → "5.1 GHz". "—" when absent/invalid (honest unknown). */
export function formatGhz(khz: number | null): string {
  if (khz === null || !isFinite(khz) || khz <= 0) return "—";
  return `${(khz / 1_000_000).toFixed(1)} GHz`;
}

/** Fraction (0..1) of the frequency bar that is the turbo tail above base.
 *  0 when either value is missing or max <= base (no visible turbo). */
export function turboFraction(baseKhz: number | null, maxKhz: number | null): number {
  if (!baseKhz || !maxKhz || maxKhz <= baseKhz) return 0;
  return clamp((maxKhz - baseKhz) / maxKhz, 0, 1);
}

/** Real threads per physical core (2 on SMT AMD, 1 on Lunar Lake / no-HT). From
 *  actual sysfs counts — never assume ×2. Falls back to 1 on missing data. */
export function threadsPerCore(cores: number | null, threads: number | null): number {
  if (!cores || !threads || threads < cores) return 1;
  return Math.max(1, Math.round(threads / cores));
}

/** Logical threads currently active: all of them with SMT on, one per core off. */
export function activeThreads(cores: number, threads: number, smtOn: boolean): number {
  return smtOn ? threads : cores;
}
