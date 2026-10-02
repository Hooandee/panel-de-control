import type { BatteryState, FanState, PowerDraw, TdpState } from "../../../src/api";

const TEMP_FLOOR_C = 30;
const TEMP_CEILING_C = 95;

const clamp01 = (value: number) => Math.max(0, Math.min(1, value));

export interface PowerReading {
  /** Big number in the ring centre: performance level on ARM, measured watts elsewhere. */
  value: number | null;
  unit: "level" | "W";
  fraction: number;
  watts: number | null;
}

export function powerReading(tdp: TdpState | null, power: PowerDraw | null): PowerReading {
  const watts = power?.watts ?? null;
  if (tdp?.unit === "level") {
    const level = tdp.supported ? tdp.watts : null;
    return { value: level, unit: "level", fraction: level ? clamp01(level / 10) : 0, watts };
  }
  const ceiling = tdp?.limits ? Math.max(tdp.limits.max, tdp.limits.max_ac) : 0;
  return { value: watts, unit: "W", fraction: watts != null && ceiling > 0 ? clamp01(watts / ceiling) : 0, watts };
}

export function hottest(fans: FanState | null): number | null {
  const temps = (fans?.temps ?? []).map((t) => t.celsius).filter((c) => Number.isFinite(c));
  return temps.length ? Math.max(...temps) : null;
}

export const tempFraction = (celsius: number | null) =>
  celsius == null ? 0 : clamp01((celsius - TEMP_FLOOR_C) / (TEMP_CEILING_C - TEMP_FLOOR_C));

export const gpuFraction = (power: PowerDraw | null) =>
  power?.gpu_busy == null ? 0 : clamp01(power.gpu_busy / 100);

export function fanRpm(fans: FanState | null): number | null {
  const rpms = (fans?.fans ?? []).map((f) => f.rpm).filter((r): r is number => r != null);
  return rpms.length ? Math.max(...rpms) : null;
}

export type BatteryMood = "charging" | "full" | "low" | "normal";

export interface BatteryReading {
  percent: number | null;
  minutesLeft: number | null;
  mood: BatteryMood;
}

export function batteryReading(state: BatteryState | null): BatteryReading {
  const battery = state?.battery;
  const percent = battery?.present ? battery.percent : null;
  const status = battery?.status ?? "";
  const charging = status === "Charging" || (battery?.ac_online === true && status !== "Full" && status !== "Discharging");
  const mood: BatteryMood = status === "Full" ? "full" : charging ? "charging" : percent != null && percent <= 20 ? "low" : "normal";
  const minutesLeft = !charging && battery?.eta_seconds ? Math.round(battery.eta_seconds / 60) : null;
  return { percent, minutesLeft, mood };
}

export function formatMinutes(minutes: number | null): string {
  if (minutes == null || minutes < 0) return "—";
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, "0")}`;
}
