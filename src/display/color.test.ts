import { describe, expect, it } from "vitest";
import {
  isNativeColor,
  isCalibrated,
  pickCalibration,
  shouldWarnHdrSaturation,
  NEUTRAL as NATIVE,
} from "./color";

describe("isNativeColor", () => {
  it("true only when every field is neutral", () => {
    expect(NATIVE.hdr_saturation).toBe(100);
    expect(isNativeColor(NATIVE)).toBe(true);
    expect(isNativeColor({ ...NATIVE, saturation: 101 })).toBe(false);
    expect(isNativeColor({ ...NATIVE, temperature: 5 })).toBe(false);
    expect(isNativeColor({ ...NATIVE, contrast: -10 })).toBe(false);
  });

  it("ignores the separate HDR saturation look", () => {
    expect(isNativeColor({ ...NATIVE, hdr_saturation: 140 })).toBe(true);
  });
});

describe("shouldWarnHdrSaturation", () => {
  it("warns on the first selectable value above 130", () => {
    expect(shouldWarnHdrSaturation(130)).toBe(false);
    expect(shouldWarnHdrSaturation(135)).toBe(true);
  });
});

describe("isCalibrated", () => {
  it("ignores saturation (that's the per-game hero, not calibration)", () => {
    expect(isCalibrated({ ...NATIVE, saturation: 160 })).toBe(false);
    expect(isCalibrated({ ...NATIVE, hdr_saturation: 140 })).toBe(false);
  });

  it("true when any calibration field deviates from neutral", () => {
    expect(isCalibrated({ ...NATIVE, temperature: -30 })).toBe(true);
    expect(isCalibrated({ ...NATIVE, contrast: 20 })).toBe(true);
    expect(isCalibrated({ ...NATIVE, gamma: 15 })).toBe(true);
    expect(isCalibrated({ ...NATIVE, hue: -10 })).toBe(true);
    expect(isCalibrated({ ...NATIVE, gain_r: 120 })).toBe(true);
    expect(isCalibrated({ ...NATIVE, vibrance: 40 })).toBe(true);
  });
});

describe("pickCalibration", () => {
  it("returns every calibration field and drops saturation", () => {
    const cal = pickCalibration({
      ...NATIVE, saturation: 160, hdr_saturation: 140,
      gamma: 20, gain_b: 130,
    });
    expect(cal).not.toHaveProperty("saturation");
    expect(cal).not.toHaveProperty("hdr_saturation");
    expect(cal.gamma).toBe(20);
    expect(cal.gain_b).toBe(130);
    expect(cal.temperature).toBe(0);
  });
});
