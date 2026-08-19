// @vitest-environment happy-dom
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getColorState: vi.fn(),
  setSaturation: vi.fn(),
  previewCalibration: vi.fn(),
  setCalibration: vi.fn(),
  discardCalibration: vi.fn(),
  resetColor: vi.fn(),
  previewOledLook: vi.fn(),
  previewColorPreset: vi.fn(),
  setColorFollowGlobal: vi.fn(),
}));

const scopeUi = vi.hoisted(() => ({
  scope: "game" as "game" | "global",
  onScope: vi.fn(),
  applyFollow: null as null | ((follow: boolean, appid: string) => Promise<boolean | void>),
}));

vi.mock("../api", () => ({
  getColorState: mocks.getColorState,
  previewCalibration: mocks.previewCalibration,
  setCalibration: mocks.setCalibration,
  discardCalibration: mocks.discardCalibration,
  setSaturation: mocks.setSaturation,
  setColorFollowGlobal: mocks.setColorFollowGlobal,
  previewOledLook: mocks.previewOledLook,
  previewColorPreset: mocks.previewColorPreset,
  resetColor: mocks.resetColor,
}));

let game = { appid: "100", liveAppid: 100, name: "First" };

vi.mock("../tdp/useRunningGame", () => ({
  useRunningGame: () => game,
}));

vi.mock("../useScopeSync", () => ({
  useScopeSync: (_appid: unknown, _follows: unknown, applyFollow: typeof scopeUi.applyFollow) => {
    scopeUi.applyFollow = applyFollow;
    return { scope: scopeUi.scope, onScope: scopeUi.onScope };
  },
}));

import { useColor } from "./useColor";

const COLOR = {
  supported: true,
  saturation: 100,
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
  has_game_profile: false,
  follows_global: true,
  appid: "100",
  oled_look: null,
  panel: "lcd",
  perf_cost: false,
  device_name: "Test",
  preview: false,
  revert_seconds: 15,
  revert_remaining: null,
  preview_scope: null,
  preview_appid: null,
  presets: ["native"],
  active_preset: "native",
};

async function settle(): Promise<void> {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("useColor preview lifecycle", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    game = { appid: "100", liveAppid: 100, name: "First" };
    scopeUi.scope = "game";
    scopeUi.applyFollow = null;
    mocks.getColorState.mockResolvedValue(COLOR);
    mocks.setSaturation.mockResolvedValue(COLOR);
    mocks.previewCalibration.mockResolvedValue({ ...COLOR, contrast: 20, preview: true });
    mocks.setCalibration.mockResolvedValue({ ...COLOR, contrast: 20 });
    mocks.discardCalibration.mockResolvedValue(COLOR);
    mocks.resetColor.mockResolvedValue(COLOR);
    mocks.previewOledLook.mockResolvedValue(COLOR);
    mocks.previewColorPreset.mockResolvedValue(COLOR);
    mocks.setColorFollowGlobal.mockResolvedValue(COLOR);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.resetAllMocks();
  });

  it("binds a queued preview to the active game context", async () => {
    const { result } = renderHook(() => useColor());
    await settle();

    act(() => result.current.onCalibration({ contrast: 20 }));
    await act(async () => vi.advanceTimersByTimeAsync(200));

    expect(mocks.previewCalibration).toHaveBeenCalledWith(
      expect.objectContaining({ contrast: 20 }),
      "game",
      "100",
      "100",
    );
  });

  it("routes saturation through the shared preview window", async () => {
    mocks.previewCalibration.mockResolvedValueOnce({
      ...COLOR, saturation: 130, preview: true, preview_scope: "game", preview_appid: "100",
    });
    const { result } = renderHook(() => useColor());
    await settle();

    act(() => result.current.onSaturation(130));
    await act(async () => vi.advanceTimersByTimeAsync(200));
    await settle();

    expect(mocks.setSaturation).not.toHaveBeenCalled();
    expect(mocks.previewCalibration).toHaveBeenCalledWith(
      expect.objectContaining({ saturation: 130 }), "game", "100", "100",
    );
    expect(result.current.revertIn).toBe(15);
  });

  it("includes saturation when confirming a color preview", async () => {
    mocks.previewCalibration.mockResolvedValueOnce({
      ...COLOR, saturation: 130, preview: true, preview_scope: "game", preview_appid: "100",
    });
    const { result } = renderHook(() => useColor());
    await settle();

    act(() => result.current.onSaturation(130));
    await act(async () => vi.advanceTimersByTimeAsync(200));
    await act(async () => result.current.confirmCalibration());

    expect(mocks.setCalibration).toHaveBeenCalledWith(
      expect.objectContaining({ saturation: 130 }), "game", "100", "100",
    );
  });

  it("previews native in the active scope before reset", async () => {
    mocks.resetColor.mockResolvedValueOnce({
      ...COLOR, preview: true, preview_scope: "game", preview_appid: "100",
    });
    const { result } = renderHook(() => useColor());
    await settle();

    act(() => result.current.onReset());
    await settle();

    expect(mocks.resetColor).toHaveBeenCalledWith("game", "100", "100");
    expect(result.current.revertIn).toBe(15);
  });

  it("discards the preview immediately through the backend", async () => {
    const { result } = renderHook(() => useColor());
    await settle();

    act(() => result.current.onCalibration({ contrast: 20 }));
    await act(async () => vi.advanceTimersByTimeAsync(200));
    await act(async () => result.current.discardCalibration());

    expect(mocks.discardCalibration).toHaveBeenCalledOnce();
    expect(result.current.revertIn).toBeNull();
    expect(result.current.state?.contrast).toBe(0);
  });

  it("refreshes until a late Gamescope backend becomes available", async () => {
    mocks.getColorState
      .mockResolvedValueOnce({ ...COLOR, supported: false })
      .mockResolvedValueOnce(COLOR);
    const { result } = renderHook(() => useColor());
    await settle();

    expect(result.current.state?.supported).toBe(false);
    await act(async () => vi.advanceTimersByTimeAsync(2_000));
    await settle();

    expect(mocks.getColorState).toHaveBeenCalledTimes(2);
    expect(result.current.state?.supported).toBe(true);
  });

  it("recovers when the initial Gamescope state request fails", async () => {
    mocks.getColorState
      .mockRejectedValueOnce(new Error("rpc failed"))
      .mockResolvedValueOnce(COLOR);
    const { result } = renderHook(() => useColor());
    await settle();

    expect(result.current.state).toBeNull();
    await act(async () => vi.advanceTimersByTimeAsync(2_000));
    await settle();

    expect(mocks.getColorState).toHaveBeenCalledTimes(2);
    expect(result.current.state?.supported).toBe(true);
  });

  it("continues probing Gamescope after a transient RPC failure", async () => {
    mocks.getColorState
      .mockResolvedValueOnce({ ...COLOR, supported: false })
      .mockRejectedValueOnce(new Error("rpc failed"))
      .mockResolvedValueOnce(COLOR);
    const { result } = renderHook(() => useColor());
    await settle();

    await act(async () => vi.advanceTimersByTimeAsync(4_000));
    await settle();

    expect(mocks.getColorState).toHaveBeenCalledTimes(3);
    expect(result.current.state?.supported).toBe(true);
  });

  it("combines saturation and calibration in one color preview", async () => {
    const { result } = renderHook(() => useColor());
    await settle();

    act(() => {
      result.current.onSaturation(130);
      result.current.onCalibration({ contrast: 20 });
    });
    await act(async () => vi.advanceTimersByTimeAsync(200));

    expect(mocks.setSaturation).not.toHaveBeenCalled();
    expect(mocks.previewCalibration).toHaveBeenCalledWith(
      expect.objectContaining({ saturation: 130, contrast: 20 }),
      "game",
      "100",
      "100",
    );
  });

  it("keeps the rollback visible when saving fails", async () => {
    mocks.setCalibration.mockRejectedValueOnce(new Error("rpc failed"));
    const { result } = renderHook(() => useColor());
    await settle();

    act(() => result.current.onCalibration({ contrast: 20 }));
    await act(async () => vi.advanceTimersByTimeAsync(200));
    mocks.getColorState.mockResolvedValue({ ...COLOR, contrast: 20, preview: true });
    await act(async () => result.current.confirmCalibration());
    await settle();

    expect(result.current.revertIn).not.toBeNull();
    expect(result.current.saving).toBe(false);
  });

  it("restores the confirmation window when mounting during a preview", async () => {
    mocks.getColorState.mockResolvedValueOnce({
      ...COLOR,
      contrast: 20,
      preview: true,
      revert_remaining: 7,
      preview_scope: "game",
      preview_appid: "100",
    });

    const { result } = renderHook(() => useColor());
    await settle();

    expect(result.current.revertIn).toBe(7);
  });

  it("restores a legacy game preview without saving it globally", async () => {
    scopeUi.scope = "global";
    mocks.getColorState.mockResolvedValueOnce({
      ...COLOR,
      contrast: 20,
      follows_global: false,
      preview: true,
      revert_remaining: 7,
      preview_scope: null,
      preview_appid: null,
    });
    const { result } = renderHook(() => useColor());
    await settle();

    await act(async () => result.current.confirmCalibration());

    expect(mocks.setCalibration).toHaveBeenCalledWith(
      expect.objectContaining({ contrast: 20 }),
      "game",
      "100",
      "100",
    );
  });

  it("discards a preview before changing its scope", async () => {
    const { result } = renderHook(() => useColor());
    await settle();

    act(() => result.current.onCalibration({ contrast: 20 }));
    await act(async () => vi.advanceTimersByTimeAsync(200));
    await act(async () => result.current.onScope("global"));
    await settle();

    expect(mocks.discardCalibration).toHaveBeenCalledWith("100");
    expect(scopeUi.onScope).toHaveBeenCalledWith("global");
  });

  it("does not change scope when discard cannot be confirmed", async () => {
    mocks.discardCalibration.mockRejectedValue(new Error("rpc failed"));
    const { result } = renderHook(() => useColor());
    await settle();

    act(() => result.current.onCalibration({ contrast: 20 }));
    await act(async () => vi.advanceTimersByTimeAsync(200));
    mocks.getColorState.mockResolvedValue({ ...COLOR, contrast: 20, preview: true });
    await act(async () => result.current.onScope("global"));
    await settle();

    expect(scopeUi.onScope).not.toHaveBeenCalled();
    expect(result.current.revertIn).not.toBeNull();
  });

  it("confirms the scope that started the preview", async () => {
    const { result, rerender } = renderHook(() => useColor());
    await settle();

    act(() => result.current.onCalibration({ contrast: 20 }));
    await act(async () => vi.advanceTimersByTimeAsync(200));
    scopeUi.scope = "global";
    rerender();
    await act(async () => result.current.confirmCalibration());

    expect(mocks.setCalibration).toHaveBeenCalledWith(
      expect.objectContaining({ contrast: 20 }),
      "game",
      "100",
      "100",
    );
  });

  it("confirms the backend discard when the countdown expires", async () => {
    const { result } = renderHook(() => useColor());
    await settle();

    act(() => result.current.onCalibration({ contrast: 20 }));
    await act(async () => vi.advanceTimersByTimeAsync(200));
    await act(async () => vi.advanceTimersByTimeAsync(15_000));
    await settle();

    expect(mocks.discardCalibration).toHaveBeenCalledWith("100");
    expect(result.current.revertIn).toBeNull();
    expect(result.current.state?.contrast).toBe(0);
  });

  it("keeps the tray visible when expiry cannot confirm discard", async () => {
    mocks.discardCalibration.mockRejectedValue(new Error("rpc failed"));
    mocks.getColorState.mockResolvedValue({ ...COLOR, contrast: 20, preview: true });
    const { result } = renderHook(() => useColor());
    await settle();

    act(() => result.current.onCalibration({ contrast: 20 }));
    await act(async () => vi.advanceTimersByTimeAsync(15_200));
    await settle();

    expect(result.current.revertIn).not.toBeNull();
    await act(async () => vi.advanceTimersByTimeAsync(10_000));
    expect(mocks.discardCalibration).toHaveBeenCalledTimes(5);
  });

  it("cancels a queued preview before preset, OLED look, or reset", async () => {
    const { result } = renderHook(() => useColor());
    await settle();

    act(() => result.current.onCalibration({ contrast: 20 }));
    act(() => result.current.onPreset("vivo"));
    await act(async () => vi.advanceTimersByTimeAsync(200));

    act(() => result.current.onCalibration({ contrast: 20 }));
    act(() => result.current.onOledLook());
    await act(async () => vi.advanceTimersByTimeAsync(200));

    act(() => result.current.onCalibration({ contrast: 20 }));
    act(() => result.current.onReset());
    await act(async () => vi.advanceTimersByTimeAsync(200));

    expect(mocks.previewCalibration).not.toHaveBeenCalled();
  });

  it("applies a preset after an in-flight preview and ignores its stale response", async () => {
    let resolvePreview!: (state: typeof COLOR) => void;
    mocks.previewCalibration.mockReturnValueOnce(new Promise((resolve) => {
      resolvePreview = resolve;
    }));
    const { result } = renderHook(() => useColor());
    await settle();

    act(() => result.current.onCalibration({ contrast: 20 }));
    await act(async () => vi.advanceTimersByTimeAsync(200));
    act(() => result.current.onPreset("vivo"));

    expect(mocks.previewColorPreset).not.toHaveBeenCalled();
    await act(async () => resolvePreview({ ...COLOR, contrast: 20, preview: true }));
    await settle();

    expect(mocks.previewColorPreset).toHaveBeenCalledOnce();
    expect(result.current.state?.preview).toBe(false);
    expect(result.current.revertIn).toBeNull();
  });

  it("waits for an in-flight preset before previewing a later slider change", async () => {
    let resolvePreset!: (state: typeof COLOR) => void;
    mocks.previewColorPreset.mockReturnValueOnce(new Promise((resolve) => {
      resolvePreset = resolve;
    }));
    const { result } = renderHook(() => useColor());
    await settle();

    act(() => result.current.onPreset("vivo"));
    act(() => result.current.onCalibration({ contrast: 20 }));
    await act(async () => vi.advanceTimersByTimeAsync(200));

    expect(mocks.previewCalibration).not.toHaveBeenCalled();
    await act(async () => resolvePreset({
      ...COLOR, saturation: 150, temperature: 10, preview: true,
    }));
    await settle();

    expect(mocks.previewCalibration).toHaveBeenCalledWith(
      expect.objectContaining({ saturation: 150, temperature: 10, contrast: 20 }),
      "game", "100", "100",
    );
  });

  it("saves the result of an in-flight preset instead of the previous color", async () => {
    let resolvePreset!: (state: typeof COLOR) => void;
    mocks.previewColorPreset.mockReturnValueOnce(new Promise((resolve) => {
      resolvePreset = resolve;
    }));
    const { result } = renderHook(() => useColor());
    await settle();

    act(() => result.current.onCalibration({ contrast: 5 }));
    await act(async () => vi.advanceTimersByTimeAsync(200));
    act(() => result.current.onPreset("vivo"));
    let confirm!: Promise<void>;
    act(() => { confirm = result.current.confirmCalibration(); });
    await act(async () => resolvePreset({
      ...COLOR, saturation: 150, temperature: 10, contrast: 20, preview: true,
    }));
    await act(async () => confirm);

    expect(mocks.setCalibration).toHaveBeenLastCalledWith(
      expect.objectContaining({ saturation: 150, temperature: 10, contrast: 20 }),
      "game", "100", "100",
    );
  });

  it("restarts the countdown when a preset replaces an existing preview", async () => {
    mocks.previewColorPreset.mockResolvedValueOnce({
      ...COLOR, saturation: 150, preview: true, revert_remaining: 15,
    });
    const { result } = renderHook(() => useColor());
    await settle();

    act(() => result.current.onCalibration({ contrast: 20 }));
    await act(async () => vi.advanceTimersByTimeAsync(200));
    await act(async () => vi.advanceTimersByTimeAsync(12_000));
    expect(result.current.revertIn).toBe(3);

    act(() => result.current.onPreset("vivo"));
    await settle();

    expect(result.current.revertIn).toBe(15);
  });

  it("restores the backend countdown when a preset request fails", async () => {
    mocks.previewColorPreset.mockRejectedValueOnce(new Error("rpc failed"));
    const { result } = renderHook(() => useColor());
    await settle();

    act(() => result.current.onCalibration({ contrast: 20 }));
    await act(async () => vi.advanceTimersByTimeAsync(200));
    await act(async () => vi.advanceTimersByTimeAsync(12_000));
    mocks.getColorState.mockResolvedValueOnce({
      ...COLOR, contrast: 20, preview: true, revert_remaining: 2,
    });

    act(() => result.current.onPreset("vivo"));
    await settle();

    expect(result.current.revertIn).toBe(2);
  });

  it("discards an in-flight preset before changing scope", async () => {
    let resolvePreset!: (state: typeof COLOR) => void;
    mocks.previewColorPreset.mockReturnValueOnce(new Promise((resolve) => {
      resolvePreset = resolve;
    }));
    const { result } = renderHook(() => useColor());
    await settle();

    act(() => result.current.onPreset("vivo"));
    act(() => result.current.onScope("global"));

    expect(scopeUi.onScope).not.toHaveBeenCalled();
    await act(async () => resolvePreset({ ...COLOR, preview: true }));
    await settle();

    expect(mocks.discardCalibration).toHaveBeenCalledWith("100");
    expect(scopeUi.onScope).toHaveBeenCalledWith("global");
  });

  it("blocks color edits until a scope change has loaded its target profile", async () => {
    let resolveFollow!: (state: typeof COLOR) => void;
    mocks.setColorFollowGlobal.mockReturnValueOnce(new Promise((resolve) => {
      resolveFollow = resolve;
    }));
    scopeUi.onScope.mockImplementationOnce(() => {
      scopeUi.scope = "global";
      void scopeUi.applyFollow?.(true, "100");
    });
    const { result, rerender } = renderHook(() => useColor());
    await settle();

    act(() => result.current.onScope("global"));
    rerender();
    act(() => result.current.onCalibration({ contrast: 20 }));
    await act(async () => vi.advanceTimersByTimeAsync(200));

    expect(mocks.previewCalibration).not.toHaveBeenCalled();
    await act(async () => resolveFollow({
      ...COLOR, appid: "100", follows_global: true, saturation: 120,
    }));
    await settle();
    act(() => result.current.onCalibration({ contrast: 20 }));
    await act(async () => vi.advanceTimersByTimeAsync(200));

    expect(mocks.previewCalibration).toHaveBeenCalledWith(
      expect.objectContaining({ saturation: 120, contrast: 20 }),
      "global", null, "100",
    );
  });

  it("rejects a new calibration while an expired discard is in flight", async () => {
    let resolveDiscard!: (state: typeof COLOR) => void;
    mocks.discardCalibration.mockReturnValueOnce(new Promise((resolve) => {
      resolveDiscard = resolve;
    }));
    const { result } = renderHook(() => useColor());
    await settle();

    act(() => result.current.onCalibration({ contrast: 20 }));
    await act(async () => vi.advanceTimersByTimeAsync(200));
    await act(async () => vi.advanceTimersByTimeAsync(15_000));
    act(() => result.current.onCalibration({ contrast: 30 }));
    await act(async () => vi.advanceTimersByTimeAsync(200));

    expect(mocks.previewCalibration).toHaveBeenCalledTimes(1);
    await act(async () => resolveDiscard(COLOR));
    expect(result.current.state?.preview).toBe(false);
  });

  it("does not let an expired preview retry discard a newer preview", async () => {
    mocks.discardCalibration.mockRejectedValue(new Error("rpc failed"));
    const { result, rerender } = renderHook(() => useColor());
    await settle();

    act(() => result.current.onCalibration({ contrast: 20 }));
    await act(async () => vi.advanceTimersByTimeAsync(200));
    mocks.getColorState.mockRejectedValue(new Error("rpc failed"));
    await act(async () => vi.advanceTimersByTimeAsync(15_000));

    game = { appid: "200", liveAppid: 200, name: "Second" };
    rerender();
    await settle();
    act(() => result.current.onCalibration({ contrast: 30 }));
    await act(async () => vi.advanceTimersByTimeAsync(1_000));

    expect(mocks.discardCalibration).toHaveBeenCalledTimes(1);
  });
});
