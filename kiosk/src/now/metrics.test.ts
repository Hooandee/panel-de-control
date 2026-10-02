import { describe, expect, it } from "vitest";

import type { BatteryState, FanState, PowerDraw, TdpState } from "../../../src/api";
import { batteryReading, fanRpm, formatMinutes, gpuFraction, hottest, powerReading, tempFraction } from "./metrics";

const tdp = (patch: Partial<TdpState>) => ({ supported: true, watts: 15, limits: { min: 5, default: 15, max: 25, max_ac: 30 }, ...patch }) as TdpState;
const power = (patch: Partial<PowerDraw>) => ({ watts: 12.5, gpu_busy: 40, ...patch }) as PowerDraw;

describe("powerReading", () => {
  it("shows the performance level on ARM and keeps measured watts aside", () => {
    expect(powerReading(tdp({ unit: "level", watts: 6 }), power({}))).toEqual({ value: 6, unit: "level", fraction: 0.6, watts: 12.5 });
  });

  it("shows measured watts against the highest limit elsewhere", () => {
    expect(powerReading(tdp({ unit: "W" }), power({ watts: 15 }))).toMatchObject({ value: 15, unit: "W", fraction: 0.5 });
  });

  it("never invents a value before the first reading", () => {
    expect(powerReading(null, null)).toEqual({ value: null, unit: "W", fraction: 0, watts: null });
  });
});

describe("sensors", () => {
  const fans = { supported: true, fans: [{ label: "a", rpm: 2100, percent: 40 }, { label: "b", rpm: null, percent: null }], temps: [{ label: "cpu", celsius: 61 }, { label: "gpu", celsius: 66.5 }] } as FanState;

  it("takes the hottest sensor and the fastest fan", () => {
    expect(hottest(fans)).toBe(66.5);
    expect(fanRpm(fans)).toBe(2100);
    expect(hottest(null)).toBeNull();
  });

  it("maps temperature and GPU load onto ring fractions", () => {
    expect(tempFraction(30)).toBe(0);
    expect(tempFraction(95)).toBe(1);
    expect(tempFraction(null)).toBe(0);
    expect(gpuFraction(power({ gpu_busy: 140 }))).toBe(1);
  });
});

describe("batteryReading", () => {
  const state = (battery: Partial<BatteryState["battery"]>) => ({ battery: { present: true, percent: 64, status: "Discharging", eta_seconds: 11_520, ac_online: false, ...battery } }) as BatteryState;

  it("reports time left only while discharging", () => {
    expect(batteryReading(state({}))).toEqual({ percent: 64, minutesLeft: 192, mood: "normal" });
    expect(batteryReading(state({ status: "Charging", ac_online: true }))).toMatchObject({ mood: "charging", minutesLeft: null });
  });

  it("flags low and full batteries", () => {
    expect(batteryReading(state({ percent: 12 })).mood).toBe("low");
    expect(batteryReading(state({ status: "Full", ac_online: true })).mood).toBe("full");
    expect(batteryReading(state({ present: false })).percent).toBeNull();
  });
});

describe("formatMinutes", () => {
  it("reads naturally", () => {
    expect(formatMinutes(42)).toBe("42 min");
    expect(formatMinutes(192)).toBe("3 h 12");
    expect(formatMinutes(null)).toBe("—");
  });
});
