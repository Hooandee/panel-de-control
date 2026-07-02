// Pure helpers for the battery card. Kept free of React/SteamClient so they're
// unit-testable and the component stays presentational.
import { clamp } from "./logic";
import { theme } from "../theme";

/** Battery fill color by charge level + charging state (charging always reads blue). */
export function batteryColor(percent: number, charging: boolean): string {
  if (charging) return theme.color.accent;
  if (percent <= 15) return theme.color.danger;
  if (percent <= 35) return theme.color.warn;
  return theme.color.ok;
}

/** Seconds → "2h 15m" / "45m". Returns "—" for null/invalid (honest unknown). */
export function formatEta(seconds: number | null): string {
  if (seconds === null || !isFinite(seconds) || seconds <= 0) return "—";
  const total = Math.round(seconds / 60);
  const h = Math.floor(total / 60);
  const m = total % 60;
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

/** Capacity chip: "52.3 / 50.2 Wh" (full / design, one unit) or "52.3 Wh" when
 *  design is absent. Compact so it fits one line. */
export function formatCapacity(fullMwh: number | null, designMwh: number | null): string {
  if (fullMwh === null || !isFinite(fullMwh)) return "—";
  const full = (fullMwh / 1000).toFixed(1);
  if (designMwh === null || !isFinite(designMwh)) return `${full} Wh`;
  return `${full} / ${(designMwh / 1000).toFixed(1)} Wh`;
}

/** Clamp a chosen charge-limit threshold into the backend's [min,max] range. */
export function clampThreshold(percent: number, min: number, max: number): number {
  return clamp(Math.round(percent), min, max);
}
