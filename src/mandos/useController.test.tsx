// @vitest-environment happy-dom
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  currentGame: null as { appid: string; name: string; liveAppid: number } | null,
  getControllerConfig: vi.fn(),
  setControllerVibration: vi.fn(),
  setControllerSetting: vi.fn(),
  setControllerButtonAction: vi.fn(),
}));

vi.mock("../tdp/useRunningGame", () => ({
  useRunningGame: () => mocks.currentGame,
}));
vi.mock("../api", () => ({
  getControllerConfig: mocks.getControllerConfig,
  getControllerDiagnostics: vi.fn(),
  resetController: vi.fn(),
  setControllerButtonAction: mocks.setControllerButtonAction,
  setControllerFollowGlobal: vi.fn(),
  setControllerSetting: mocks.setControllerSetting,
  setControllerVibration: mocks.setControllerVibration,
  testControllerVibration: vi.fn(),
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
