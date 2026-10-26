import { describe, expect, it, vi } from "vitest";

vi.mock("@decky/api", () => ({ callable: () => async () => ({}) }));
vi.mock("@decky/ui", () => ({ PanelSectionRow: () => null, DialogButton: () => null, Focusable: () => null, SliderField: () => null }));

import type { FanTargetState } from "../api";
import { activePreset } from "./FanTargetCard";

const state: FanTargetState = {
  supported: true,
  celsius: 80,
  target: null,
  min: 50,
  max: 90,
  default: 80,
  presets: [
    { id: "quiet", celsius: 85 },
    { id: "balanced", celsius: 80 },
    { id: "cool", celsius: 70 },
    { id: "max", celsius: 50 },
  ],
};

describe("activePreset", () => {
  it("names the preset that holds the current target", () => {
    expect(activePreset(state, 80)).toBe("balanced");
    expect(activePreset(state, 50)).toBe("max");
  });

  it("falls back to custom for values between presets or unknown", () => {
    expect(activePreset(state, 77)).toBe("custom");
    expect(activePreset(state, null)).toBe("custom");
  });
});
