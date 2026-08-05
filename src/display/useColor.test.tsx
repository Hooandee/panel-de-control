// @vitest-environment happy-dom
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  game: { appid: "42", name: "Game", liveAppid: 42 },
  getColorState: vi.fn(),
  setSaturation: vi.fn(),
  setHdrSaturation: vi.fn(),
  setColorFollowGlobal: vi.fn(),
  applyColorPreset: vi.fn(),
  resetColor: vi.fn(),
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
  applyColorPreset: mocks.applyColorPreset,
  resetColor: mocks.resetColor,
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
    mocks.applyColorPreset.mockResolvedValue(state);
    mocks.resetColor.mockResolvedValue(state);
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
    await act(async () => {
      hook.unmount();
      await Promise.resolve();
    });

    expect(mocks.setHdrSaturation).toHaveBeenCalledTimes(1);
    expect(mocks.setHdrSaturation).toHaveBeenCalledWith(135, "global", null);
  });

  it("flushes a pending SDR value when Pantalla unmounts", async () => {
    const hook = renderHook(() => useColor());
    await act(async () => { await Promise.resolve(); });

    act(() => hook.result.current.onSaturation(130));
    await act(async () => {
      hook.unmount();
      await Promise.resolve();
    });

    expect(mocks.setSaturation).toHaveBeenCalledTimes(1);
    expect(mocks.setSaturation).toHaveBeenCalledWith(130, "global", null);
  });

  it("persists a pending drag before changing scope", async () => {
    let finishSave: ((value: typeof state) => void) | undefined;
    mocks.setHdrSaturation.mockImplementation(() => new Promise((resolve) => {
      finishSave = resolve;
    }));
    const hook = renderHook(() => useColor());
    await act(async () => { await Promise.resolve(); });

    act(() => hook.result.current.onHdrSaturation(135));
    act(() => hook.result.current.onScope("game"));
    await act(async () => { await Promise.resolve(); });

    expect(mocks.setHdrSaturation).toHaveBeenCalledWith(135, "global", null);
    expect(mocks.setColorFollowGlobal).not.toHaveBeenCalled();

    await act(async () => {
      finishSave?.({ ...state, hdr_saturation: 135 });
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(mocks.setColorFollowGlobal).toHaveBeenCalledWith(false, "42");
  });

  it("does not let a pending game drag undo switching to global", async () => {
    mocks.getColorState.mockResolvedValue({
      ...state, follows_global: false, has_game_profile: true,
    });
    const hook = renderHook(() => useColor());
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    act(() => hook.result.current.onHdrSaturation(135));
    act(() => hook.result.current.onScope("global"));
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(mocks.setHdrSaturation).toHaveBeenCalledWith(135, "game", "42");
    expect(mocks.setHdrSaturation.mock.invocationCallOrder[0]).toBeLessThan(
      mocks.setColorFollowGlobal.mock.invocationCallOrder[0],
    );
    expect(mocks.setColorFollowGlobal).toHaveBeenCalledWith(true, "42");
  });

  it("persists pending saturation before preset and reset actions", async () => {
    const hook = renderHook(() => useColor());
    await act(async () => { await Promise.resolve(); });

    act(() => {
      hook.result.current.onSaturation(125);
      hook.result.current.onPreset("native");
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(mocks.setSaturation.mock.invocationCallOrder[0]).toBeLessThan(
      mocks.applyColorPreset.mock.invocationCallOrder[0],
    );

    act(() => {
      hook.result.current.onHdrSaturation(130);
      hook.result.current.onReset();
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(mocks.setHdrSaturation.mock.invocationCallOrder[0]).toBeLessThan(
      mocks.resetColor.mock.invocationCallOrder[0],
    );
  });
});
