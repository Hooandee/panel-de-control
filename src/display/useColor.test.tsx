// @vitest-environment happy-dom
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  game: { appid: "42", name: "Game", liveAppid: 42 },
  getColorState: vi.fn(),
  setSaturation: vi.fn(),
  setHdrSaturation: vi.fn(),
  setColorFollowGlobal: vi.fn(),
}));

vi.mock("../tdp/useRunningGame", () => ({
  useRunningGame: () => mocks.game,
}));
vi.mock("../api", () => ({
  getColorState: mocks.getColorState,
  setHdrSaturation: mocks.setHdrSaturation,
  setColorFollowGlobal: mocks.setColorFollowGlobal,
  setSaturation: mocks.setSaturation,
  previewCalibration: vi.fn(),
  setCalibration: vi.fn(),
  applyOledLook: vi.fn(),
  applyColorPreset: vi.fn(),
  resetColor: vi.fn(),
}));

import { useColor } from "./useColor";

const state = {
  supported: true,
  saturation: 100,
  hdr_saturation: 100,
  temperature: 0,
  contrast: 0,
  gamma: 0,
  hue: 0,
  black: 0,
  gain_r: 100,
  gain_g: 100,
  gain_b: 100,
  vibrance: 0,
  global_saturation: 100,
  global_hdr_saturation: 100,
  hdr_saturation_supported: true,
  hdr_saturation_experimental: true,
  has_game_profile: false,
  follows_global: true,
  appid: "42",
  oled_look: null,
  panel: "oled",
  preview: false,
  revert_seconds: 15,
  perf_cost: false,
  device_name: "Legion Go 2",
  presets: ["native"],
  active_preset: "native",
};

describe("useColor HDR saturation", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    vi.clearAllMocks();
    mocks.getColorState.mockResolvedValue(state);
    mocks.setColorFollowGlobal.mockResolvedValue(state);
    mocks.setSaturation.mockResolvedValue({ ...state, saturation: 130 });
    mocks.setHdrSaturation.mockResolvedValue({
      ...state, hdr_saturation: 140,
    });
  });

  afterEach(() => vi.useRealTimers());

  it("debounces the latest value into the selected game profile", async () => {
    const hook = renderHook(() => useColor());
    await act(async () => { await Promise.resolve(); });

    act(() => hook.result.current.onScope("game"));
    act(() => {
      hook.result.current.onHdrSaturation(125);
      hook.result.current.onHdrSaturation(140);
      vi.advanceTimersByTime(199);
    });
    expect(mocks.setHdrSaturation).not.toHaveBeenCalled();

    await act(async () => {
      vi.advanceTimersByTime(1);
      await Promise.resolve();
    });
    expect(mocks.setHdrSaturation).toHaveBeenCalledWith(140, "game", "42");
  });

  it("persists SDR and HDR drags independently", async () => {
    const hook = renderHook(() => useColor());
    await act(async () => { await Promise.resolve(); });

    act(() => {
      hook.result.current.onSaturation(130);
      hook.result.current.onHdrSaturation(140);
    });
    await act(async () => {
      vi.advanceTimersByTime(200);
      await Promise.resolve();
    });

    expect(mocks.setSaturation).toHaveBeenCalledWith(130, "global", null);
    expect(mocks.setHdrSaturation).toHaveBeenCalledWith(140, "global", null);
  });

  it("flushes a pending HDR value when Pantalla unmounts", async () => {
    const hook = renderHook(() => useColor());
    await act(async () => { await Promise.resolve(); });

    act(() => hook.result.current.onHdrSaturation(135));
    act(() => hook.unmount());

    expect(mocks.setHdrSaturation).toHaveBeenCalledTimes(1);
    expect(mocks.setHdrSaturation).toHaveBeenCalledWith(135, "global", null);
  });

  it("flushes a pending SDR value when Pantalla unmounts", async () => {
    const hook = renderHook(() => useColor());
    await act(async () => { await Promise.resolve(); });

    act(() => hook.result.current.onSaturation(130));
    act(() => hook.unmount());

    expect(mocks.setSaturation).toHaveBeenCalledTimes(1);
    expect(mocks.setSaturation).toHaveBeenCalledWith(130, "global", null);
  });
});
