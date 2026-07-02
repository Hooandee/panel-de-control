import { describe, expect, it } from "vitest";
import { batteryColor, batteryStatusKey, clampThreshold, formatCapacity, formatEta } from "./battery";
import { theme } from "../theme";

describe("batteryColor", () => {
  it("is blue while charging regardless of level", () => {
    expect(batteryColor(5, true)).toBe(theme.color.accent);
    expect(batteryColor(90, true)).toBe(theme.color.accent);
  });
  it("is red when low, amber mid, green high (discharging)", () => {
    expect(batteryColor(10, false)).toBe(theme.color.danger);
    expect(batteryColor(30, false)).toBe(theme.color.warn);
    expect(batteryColor(80, false)).toBe(theme.color.ok);
  });
});

describe("formatEta", () => {
  it("formats hours and minutes", () => {
    expect(formatEta(7200)).toBe("2h 0m");
    expect(formatEta(8100)).toBe("2h 15m");
  });
  it("formats minutes only under an hour", () => {
    expect(formatEta(2700)).toBe("45m");
  });
  it("returns dash for null/invalid", () => {
    expect(formatEta(null)).toBe("—");
    expect(formatEta(0)).toBe("—");
    expect(formatEta(-5)).toBe("—");
  });
});

describe("formatCapacity", () => {
  it("shows full / design with a single unit", () => {
    expect(formatCapacity(52349, 50207)).toBe("52.3 / 50.2 Wh");
  });
  it("shows full only when design is absent", () => {
    expect(formatCapacity(48000, null)).toBe("48.0 Wh");
  });
  it("returns dash when full is absent", () => {
    expect(formatCapacity(null, 50000)).toBe("—");
  });
});

describe("batteryStatusKey", () => {
  it("is charging when Charging", () => {
    expect(batteryStatusKey("Charging", false)).toBe("charging");
  });
  it("is connected when Full, or on AC and not discharging", () => {
    expect(batteryStatusKey("Full", false)).toBe("connected");
    expect(batteryStatusKey("Not charging", true)).toBe("connected");
  });
  it("is discharging otherwise (incl. on AC but Discharging)", () => {
    expect(batteryStatusKey("Discharging", false)).toBe("discharging");
    expect(batteryStatusKey("Discharging", true)).toBe("discharging");
    expect(batteryStatusKey(null, false)).toBe("discharging");
  });
});

describe("clampThreshold", () => {
  it("clamps into range and rounds", () => {
    expect(clampThreshold(150, 20, 100)).toBe(100);
    expect(clampThreshold(10, 20, 100)).toBe(20);
    expect(clampThreshold(79.6, 20, 100)).toBe(80);
  });
});

