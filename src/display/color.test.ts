import { describe, expect, it } from "vitest";
import {
  SATURATION_CHIPS,
  activeSaturationChip,
  isNativeColor,
  isCalibrated,
} from "./color";

const NATIVE = { saturation: 100, temperature: 0, contrast: 0 };

describe("saturation chips", () => {
  it("includes a native (100%) preset first", () => {
    expect(SATURATION_CHIPS[0]).toEqual({ key: "native", value: 100 });
  });

  it("matches a value exactly to its chip", () => {
    const vivid = SATURATION_CHIPS.find((c) => c.key === "vivid")!;
    expect(activeSaturationChip(vivid.value)).toBe("vivid");
    expect(activeSaturationChip(100)).toBe("native");
  });

  it("returns null (custom) for an off-preset value", () => {
    expect(activeSaturationChip(137)).toBeNull();
  });
});

describe("isNativeColor", () => {
  it("true only when every field is neutral", () => {
    expect(isNativeColor(NATIVE)).toBe(true);
    expect(isNativeColor({ ...NATIVE, saturation: 101 })).toBe(false);
    expect(isNativeColor({ ...NATIVE, temperature: 5 })).toBe(false);
    expect(isNativeColor({ ...NATIVE, contrast: -10 })).toBe(false);
  });
});

describe("isCalibrated", () => {
  it("ignores saturation (that's the per-game hero, not calibration)", () => {
    expect(isCalibrated({ ...NATIVE, saturation: 160 })).toBe(false);
  });

  it("true when temperature/contrast deviate from neutral", () => {
    expect(isCalibrated({ ...NATIVE, temperature: -30 })).toBe(true);
    expect(isCalibrated({ ...NATIVE, contrast: 20 })).toBe(true);
  });
});
