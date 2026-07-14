import { describe, it, expect } from "vitest";
import { fanCurveNotice } from "./notice";
import type { FanCurveState } from "../api";

// Echo translator: returns "key" or "key|param=value" so assertions stay simple.
const t = (key: string, params?: Record<string, string | number>) =>
  params ? `${key}|${Object.entries(params).map(([k, v]) => `${k}=${v}`).join(",")}` : key;

const base = { supported: false, firmware_mode: null, has_firmware_modes: false, os_name: null } as unknown as FanCurveState;

describe("fanCurveNotice", () => {
  it("names the active firmware mode when one governs the fan", () => {
    expect(fanCurveNotice({ ...base, firmware_mode: "performance" }, t))
      .toBe("fans.curve.governed|mode=tdp.fwmode.performance");
  });

  it("points to TDP modes in custom on a firmware-mode device", () => {
    expect(fanCurveNotice({ ...base, has_firmware_modes: true }, t)).toBe("fans.curve.custom_mode");
  });

  it("falls back to the OS-named note otherwise", () => {
    expect(fanCurveNotice({ ...base, os_name: "CachyOS" }, t)).toBe("fans.curve.unsupported|os=CachyOS");
  });

  it("uses the generic system label when the OS is unknown", () => {
    expect(fanCurveNotice(base, t)).toBe("fans.curve.unsupported|os=fans.curve.thisSystem");
  });
});
