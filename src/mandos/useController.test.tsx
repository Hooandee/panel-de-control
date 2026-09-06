// @vitest-environment happy-dom
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getControllerConfig: vi.fn(),
  runControllerAction: vi.fn(),
  runningGame: null as null | { appid: string },
}));

vi.mock("../api", () => ({
  getControllerConfig: mocks.getControllerConfig,
  runControllerAction: mocks.runControllerAction,
  resetController: vi.fn(),
  setControllerButton: vi.fn(),
  setControllerFollowGlobal: vi.fn(),
  setControllerSetting: vi.fn(),
}));

vi.mock("./useRunningGame", () => ({ useRunningGame: () => mocks.runningGame }));
vi.mock("../tdp/useRunningGame", () => ({ useRunningGame: () => mocks.runningGame }));
vi.mock("../useScopeSync", () => ({
  useScopeSync: () => ({ scope: "global", onScope: vi.fn() }),
}));

import { useController } from "./useController";

const initial = {
  manager: "hhd" as const,
  manager_version: "4.1.5",
  supported: true,
  kind: "settings" as const,
  magic_modules: {
    supported: true,
    source: "hhd" as const,
    left: "connected" as const,
    right: "connected" as const,
    busy: false,
  },
};

async function settle(): Promise<void> {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("useController hardware actions", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
    mocks.runningGame = null;
  });

  it("allows one action at a time and replaces config with the physical readback", async () => {
    let resolveAction: ((value: unknown) => void) | undefined;
    mocks.getControllerConfig.mockResolvedValue(initial);
    mocks.runControllerAction.mockImplementation(() => new Promise((resolve) => {
      resolveAction = resolve;
    }));
    const { result } = renderHook(() => useController());
    await settle();

    act(() => {
      result.current.onAction("eject_left");
      result.current.onAction("eject_right");
    });

    expect(mocks.runControllerAction).toHaveBeenCalledTimes(1);
    expect(mocks.runControllerAction).toHaveBeenCalledWith("eject_left");
    expect(result.current.actionPending).toBe("eject_left");

    resolveAction?.({
      action: "eject_left",
      outcome: "confirmed",
      accepted: true,
      modules: { ...initial.magic_modules, left: "disconnected" },
      config: {
        ...initial,
        magic_modules: { ...initial.magic_modules, left: "disconnected" },
      },
    });
    await settle();

    expect(result.current.actionPending).toBeNull();
    expect(result.current.actionResult?.outcome).toBe("confirmed");
    expect(result.current.config?.magic_modules?.left).toBe("disconnected");
  });

  it("keeps the hardware-action lock when the running game changes", async () => {
    let resolveAction: ((value: unknown) => void) | undefined;
    mocks.getControllerConfig.mockResolvedValue(initial);
    mocks.runControllerAction.mockImplementation(() => new Promise((resolve) => {
      resolveAction = resolve;
    }));
    const { result, rerender, unmount } = renderHook(() => useController());
    await settle();

    act(() => result.current.onAction("eject_left"));
    mocks.runningGame = { appid: "42" };
    rerender();
    await settle();
    act(() => result.current.onAction("eject_right"));

    expect(mocks.runControllerAction).toHaveBeenCalledTimes(1);
    expect(result.current.actionPending).toBe("eject_left");

    unmount();
    resolveAction?.({
      action: "eject_left",
      outcome: "unverifiable",
      accepted: null,
      config: initial,
    });
    await settle();
  });

  it("re-reads a known InputPlumber device briefly after boot without inventing paddles", async () => {
    vi.useFakeTimers();
    const waiting = {
      ...initial,
      manager: "inputplumber" as const,
      kind: "remap" as const,
      device_key: "zotac_gaming_zone",
      device_known: true,
      buttons: [],
    };
    const ready = {
      ...waiting,
      buttons: [{ source: "LeftPaddle1", label: "L", target: null }],
    };
    mocks.getControllerConfig.mockResolvedValueOnce(waiting).mockResolvedValueOnce(ready);
    const { result } = renderHook(() => useController());
    await settle();

    expect(result.current.config?.buttons).toEqual([]);
    await act(async () => vi.advanceTimersByTimeAsync(2_000));
    await settle();

    expect(mocks.getControllerConfig).toHaveBeenCalledTimes(2);
    expect(result.current.config?.buttons?.[0]?.label).toBe("L");
  });

  it("does not poll other known InputPlumber devices when they expose no buttons", async () => {
    vi.useFakeTimers();
    mocks.getControllerConfig.mockResolvedValue({
      ...initial,
      manager: "inputplumber" as const,
      kind: "remap" as const,
      device_key: "msi_claw_8_ai_plus",
      device_known: true,
      buttons: [],
    });
    renderHook(() => useController());
    await settle();

    await act(async () => vi.advanceTimersByTimeAsync(12_000));

    expect(mocks.getControllerConfig).toHaveBeenCalledTimes(1);
  });
});
