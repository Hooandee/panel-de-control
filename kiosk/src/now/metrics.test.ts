import { describe, expect, it } from "vitest";

import type { BatteryState, FanState } from "../../../src/api";
import { batteryReading, fanRpm, formatMinutes, hottest } from "./metrics";


describe("sensors", () => {
  const fans = { supported: true, fans: [{ label: "a", rpm: 2100, percent: 40 }, { label: "b", rpm: null, percent: null }], temps: [{ label: "cpu", celsius: 61 }, { label: "gpu", celsius: 66.5 }] } as FanState;

  it("takes the hottest sensor and the fastest fan", () => {
    expect(hottest(fans)).toBe(66.5);
    expect(fanRpm(fans)).toBe(2100);
    expect(hottest(null)).toBeNull();
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
