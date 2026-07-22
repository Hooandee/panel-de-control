import { describe, expect, it } from "vitest";

import type { DeviceInfo } from "../api";
import { coloresCardState, deviceHasRgb } from "./colores";

const device = (key: string): DeviceInfo => ({
  key,
  display_name: key,
  chip: "",
  vendor: "amd",
  tdp_min: 0,
  tdp_default: 0,
  tdp_max: 0,
  tdp_max_charger: 0,
  is_generic: false,
  experimental: false,
  cooler_max: null,
  gpu_gen: "unknown",
  charger_only_extra: false,
});

describe("deviceHasRgb", () => {
  it("is false while the device is still loading", () => {
    expect(deviceHasRgb(null)).toBe(false);
  });

  it("is false for both Steam Deck variants (no RGB LEDs)", () => {
    expect(deviceHasRgb(device("steam_deck_lcd"))).toBe(false);
    expect(deviceHasRgb(device("steam_deck_oled"))).toBe(false);
  });

  it("is true for other handhelds and the generic fallback", () => {
    expect(deviceHasRgb(device("rog_xbox_ally_x"))).toBe(true);
    expect(deviceHasRgb(device("legion_go_2"))).toBe(true);
    expect(deviceHasRgb(device("generic"))).toBe(true);
  });
});

describe("coloresCardState", () => {
  it("hides on a device without RGB regardless of install/phase", () => {
    expect(coloresCardState({ hasRgb: false, installed: true, phase: "idle" })).toBe("hidden");
    expect(coloresCardState({ hasRgb: false, installed: false, phase: "installing" })).toBe("hidden");
  });

  it("shows install when RGB-capable but Colores is missing", () => {
    expect(coloresCardState({ hasRgb: true, installed: false, phase: "idle" })).toBe("install");
  });

  it("shows open once Colores is installed", () => {
    expect(coloresCardState({ hasRgb: true, installed: true, phase: "idle" })).toBe("open");
  });

  it("reflects the in-flight install phase over the install/open states", () => {
    expect(coloresCardState({ hasRgb: true, installed: false, phase: "installing" })).toBe("installing");
    expect(coloresCardState({ hasRgb: true, installed: false, phase: "error" })).toBe("error");
  });
});
