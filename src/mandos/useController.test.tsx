// @vitest-environment happy-dom
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  currentGame: null as { appid: string; name: string; liveAppid: number } | null,
  getControllerConfig: vi.fn(),
  setControllerVibration: vi.fn(),
  setControllerSetting: vi.fn(),
  setControllerButtonAction: vi.fn(),
  setControllerVirtualMode: vi.fn(),
  testControllerVibration: vi.fn(),
}));

vi.mock("../tdp/useRunningGame", () => ({
  useRunningGame: () => mocks.currentGame,
}));
vi.mock("../api", () => ({
  getControllerConfig: mocks.getControllerConfig,
  getControllerDiagnostics: vi.fn(),
  resetController: vi.fn(),
  setControllerButtonAction: mocks.setControllerButtonAction,
  setControllerVirtualMode: mocks.setControllerVirtualMode,
  setControllerFollowGlobal: vi.fn(),
  setControllerSetting: mocks.setControllerSetting,
  setControllerVibration: mocks.setControllerVibration,
  testControllerVibration: mocks.testControllerVibration,
}));

import { useController } from "./useController";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

function config(version: string) {
  return {
    manager: "inputplumber",
    manager_version: version,
    supported: true,
    kind: "remap",
    follows_global: true,
  };
}

describe("useController request coordination", () => {
  beforeEach(() => {
    mocks.currentGame = { appid: "10", name: "First", liveAppid: 10 };
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("ignores a response from the previous game", async () => {
    const first = deferred<ReturnType<typeof config>>();
    const second = deferred<ReturnType<typeof config>>();
    mocks.getControllerConfig
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    const hook = renderHook(() => useController());

    mocks.currentGame = { appid: "20", name: "Second", liveAppid: 20 };
    hook.rerender();
    await act(async () => {
      first.resolve(config("old"));
      await Promise.resolve();
    });
    expect(hook.result.current.config).toBeNull();

    await act(async () => {
      second.resolve(config("new"));
      await Promise.resolve();
    });
    expect(hook.result.current.config?.manager_version).toBe("new");
  });

  it("debounces continuous vibration writes and keeps the latest value", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    mocks.getControllerConfig.mockResolvedValue(config("current"));
    mocks.setControllerVibration.mockResolvedValue(config("applied"));
    const { result } = renderHook(() => useController());
    await act(async () => { await Promise.resolve(); });

    act(() => {
      result.current.onSetVibration({ value: 20 });
      result.current.onSetVibration({ value: 40 });
      result.current.onSetVibration({ value: 60 });
      vi.advanceTimersByTime(149);
    });
    expect(mocks.setControllerVibration).not.toHaveBeenCalled();

    await act(async () => {
      vi.advanceTimersByTime(1);
      await Promise.resolve();
    });
    expect(mocks.setControllerVibration).toHaveBeenCalledTimes(1);
    expect(mocks.setControllerVibration).toHaveBeenCalledWith(
      { value: 60 }, "global", null,
    );
  });

  it("applies vibration toggles immediately", async () => {
    mocks.getControllerConfig.mockResolvedValue(config("current"));
    mocks.setControllerVibration.mockResolvedValue(config("applied"));
    const { result } = renderHook(() => useController());
    await act(async () => { await Promise.resolve(); });

    act(() => result.current.onSetVibration({ enabled: false }));

    expect(mocks.setControllerVibration).toHaveBeenCalledWith(
      { enabled: false }, "global", null,
    );
  });

  it("debounces and merges Lenovo HD enum changes in the active scope", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    mocks.getControllerConfig.mockResolvedValue(config("current"));
    mocks.setControllerVibration.mockResolvedValue(config("applied"));
    const { result } = renderHook(() => useController());
    await act(async () => { await Promise.resolve(); });

    act(() => {
      result.current.onSetVibration({ intensity: "high" });
      result.current.onSetVibration({ left_pattern: "racing" });
      result.current.onSetVibration({ right_pattern: "rpg" });
      vi.advanceTimersByTime(149);
    });
    expect(mocks.setControllerVibration).not.toHaveBeenCalled();

    await act(async () => {
      vi.advanceTimersByTime(1);
      await Promise.resolve();
    });
    expect(mocks.setControllerVibration).toHaveBeenCalledWith(
      { intensity: "high", left_pattern: "racing", right_pattern: "rpg" },
      "global",
      null,
    );
  });

  it("flushes a pending Lenovo enum together with a touchpad toggle", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    mocks.getControllerConfig.mockResolvedValue(config("current"));
    mocks.setControllerVibration.mockResolvedValue(config("applied"));
    const { result } = renderHook(() => useController());
    await act(async () => { await Promise.resolve(); });

    act(() => {
      result.current.onSetVibration({ touchpad_intensity: "off" });
      result.current.onSetVibration({ touchpad_enabled: false });
    });

    expect(mocks.setControllerVibration).toHaveBeenCalledTimes(1);
    expect(mocks.setControllerVibration).toHaveBeenCalledWith(
      { touchpad_intensity: "off", touchpad_enabled: false },
      "global",
      null,
    );
  });

  it("sends a keyboard chord as one ordered action", async () => {
    mocks.getControllerConfig.mockResolvedValue(config("current"));
    mocks.setControllerButtonAction.mockResolvedValue(config("applied"));
    const { result } = renderHook(() => useController());
    await act(async () => { await Promise.resolve(); });

    act(() => result.current.onSetButtonAction("extra_l1", {
      kind: "keyboard_chord",
      keys: ["KeyLeftCtrl", "KeyTab"],
    }));

    expect(mocks.setControllerButtonAction).toHaveBeenCalledWith(
      "extra_l1",
      { kind: "keyboard_chord", keys: ["KeyLeftCtrl", "KeyTab"] },
      "global",
      null,
    );
  });

  it("keeps the structured stop failure from a motor test", async () => {
    mocks.getControllerConfig.mockResolvedValue(config("current"));
    mocks.testControllerVibration.mockResolvedValue({
      sent: true,
      stopped: false,
      restored: true,
      reason: "stop_failed",
    });
    const { result } = renderHook(() => useController());
    await act(async () => { await Promise.resolve(); });

    await act(async () => {
      result.current.onTestVibration("pulse", "left", 50);
      await Promise.resolve();
    });

    expect(mocks.testControllerVibration).toHaveBeenCalledWith(
      "pulse", "left", 50,
    );
    expect(result.current.vibrationTestResult?.reason).toBe("stop_failed");
  });

  it("persists the selected virtual mode in the active game scope", async () => {
    mocks.getControllerConfig.mockResolvedValue(config("current"));
    mocks.setControllerVirtualMode.mockResolvedValue(config("applied"));
    const { result } = renderHook(() => useController());
    await act(async () => { await Promise.resolve(); });

    act(() => result.current.onSetVirtualMode("dualsense"));

    expect(mocks.setControllerVirtualMode).toHaveBeenCalledWith(
      "dualsense", "global", null,
    );
  });

  it("ignores an older mutation response from the same game", async () => {
    const first = deferred<ReturnType<typeof config>>();
    const second = deferred<ReturnType<typeof config>>();
    mocks.getControllerConfig.mockResolvedValue(config("initial"));
    mocks.setControllerSetting
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    const { result } = renderHook(() => useController());
    await act(async () => { await Promise.resolve(); });

    act(() => {
      result.current.onSetSetting("mode", "uinput");
      result.current.onSetSetting("mode", "dualsense");
    });
    await act(async () => {
      second.resolve(config("new"));
      await Promise.resolve();
      first.resolve(config("old"));
      await Promise.resolve();
    });

    expect(result.current.config?.manager_version).toBe("new");
  });
});
