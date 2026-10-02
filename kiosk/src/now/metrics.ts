import type { BatteryState, FanState } from "../../../src/api";

export function hottest(fans: FanState | null): number | null {
  const temps = (fans?.temps ?? []).map((t) => t.celsius).filter((c) => Number.isFinite(c));
  return temps.length ? Math.max(...temps) : null;
}

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
