import { describe, expect, it } from "vitest";

import type { TdpState } from "../../../src/api";
import {
  coloresEffects, coloresModes, coloresTarget, ColoresState, formatPlaying, fpsChoices, levelCaption,
  lightsSwatch, pacePath, pushSample, refreshChoices, stepAt, stepRange,
} from "./deckMath";

const tdp = { limits: { min: 1, default: 6, max: 10, max_ac: 10 }, level_frequencies: { "6": { cpu_khz: [1459200, 2054400, 2227200], gpu_mhz: 475 } } } as unknown as TdpState;

const lights = (patch: Partial<ColoresState> = {}): ColoresState => ({
  power: true,
  brightness: 180,
  mode: "effect",
  color: { r: 10, g: 132, b: 255 },
  gradient: [{ r: 255, g: 0, b: 0 }, { r: 0, g: 0, b: 255 }],
  effect: { id: "rainbow", speed: 50, useGradient: false },
  capabilities: { color: true, zones: 4, maxBrightness: 255, supportedEffects: ["breathing", "rainbow", "wave", "cycle"] },
  ...patch,
});

describe("performance steps", () => {
  it("uses the charger ceiling only on AC", () => {
    const watts = { limits: { min: 5, default: 15, max: 25, max_ac: 30 } } as TdpState;
    expect(stepRange(watts, false)).toEqual({ min: 5, max: 25 });
    expect(stepRange(watts, true)).toEqual({ min: 5, max: 30 });
  });

  it("maps a finger to a whole step, ignoring the padded edges", () => {
    expect(stepAt(0, 520, 11, 1, 10)).toBe(1);
    expect(stepAt(520, 520, 11, 1, 10)).toBe(10);
    expect(stepAt(11 + (498 * 5) / 9, 520, 11, 1, 10)).toBe(6);
  });

  it("reads level frequencies from the backend table only", () => {
    expect(levelCaption(tdp, 6, "es")).toBe("2,2 GHz · 475 MHz");
    expect(levelCaption(tdp, 7, "es")).toBe("");
  });
});

describe("header", () => {
  it("keeps a bounded history", () => {
    expect(pushSample([1, 2, 3], 4, 3)).toEqual([2, 3, 4]);
  });

  it("draws the pacing line under a target that sits near the top", () => {
    const { line, targetY } = pacePath([60, 60, 30, 60], 60, 300, 24);
    expect(line.startsWith("M0.0,")).toBe(true);
    expect(targetY).toBeCloseTo(24 - 24 / 1.08, 1);
    expect(pacePath([60], null, 300, 24)).toEqual({ line: "", targetY: null });
  });

  it("only shows session time once there is a minute to show", () => {
    expect(formatPlaying(null)).toBeNull();
    expect(formatPlaying(42)).toBeNull();
    expect(formatPlaying(8 * 60 + 5)).toBe("8 min");
    expect(formatPlaying(72 * 60)).toBe("1 h 12 min");
  });
});

describe("choices", () => {
  it("offers frame-rate targets the device can reach", () => {
    expect(fpsChoices(60)).toEqual([30, 40, 45, 60]);
    expect(fpsChoices(120)).toEqual([30, 40, 60, 90, 120]);
    expect(fpsChoices(null)).toEqual([30, 40, 45, 60]);
  });

  it("offers the panel's real refresh range", () => {
    expect(refreshChoices({ min: 60, max: 120 })).toEqual([60, 90, 120]);
    expect(refreshChoices({ min: 40, max: 60 })).toEqual([40, 60]);
    expect(refreshChoices({ min: null, max: 120 })).toEqual([]);
    expect(refreshChoices(null)).toEqual([]);
  });
});

describe("lights", () => {
  it("lists the same modes Colores shows for these capabilities", () => {
    expect(coloresModes({ color: true, zones: 4, batteryMode: true, audioMode: true, ambilight: true }))
      .toEqual(["solid", "gradient", "effect", "battery", "vu", "ambient"]);
    expect(coloresModes({ color: false })).toEqual([]);
    expect(coloresModes(null)).toEqual([]);
  });

  it("only offers the effects the device supports", () => {
    expect(coloresEffects(lights().capabilities)).toEqual(["breathing", "rainbow", "wave", "cycle"]);
    expect(coloresEffects({})).toHaveLength(9);
  });

  it("writes to the profile that is lit", () => {
    expect(coloresTarget(lights())).toEqual(["global", null]);
    expect(coloresTarget(lights({ profileContext: { scope: "game", appKey: "620", followsGlobal: false } }))).toEqual(["game", "620"]);
    expect(coloresTarget(lights({ profileContext: { scope: "game", appKey: "620", followsGlobal: true } }))).toEqual(["global", null]);
  });

  it("paints the strip like the lights look", () => {
    expect(lightsSwatch(null)).toBeNull();
    expect(lightsSwatch(lights({ power: false }))).toBeNull();
    expect(lightsSwatch(lights({ mode: "solid" }))).toBe("rgb(10,132,255)");
    expect(lightsSwatch(lights({ mode: "gradient" }))).toBe("linear-gradient(90deg,rgb(255,0,0),rgb(0,0,255))");
    expect(lightsSwatch(lights())).toContain("linear-gradient");
  });
});
