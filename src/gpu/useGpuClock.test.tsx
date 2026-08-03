// @vitest-environment happy-dom
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { GpuClockState } from "../api";
import type { RunningGame } from "../tdp/useRunningGame";

let runningGame: RunningGame | null = { appid: "42", liveAppid: 42, name: "Game" };

const GPU_STATE: GpuClockState = {
  supported: true,
  manual: false,
  range_min: 200,
  range_max: 2_700,
  min: 200,
  max: 2_700,
  configured_min: null,
  configured_max: null,
  requested_min: null,
  requested_max: null,
  applied_min: 200,
  applied_max: 2_700,
  generation: 0,
  status: "auto",
  reason: null,
  follows_global: true,
  has_game_profile: false,
};

const mocks = vi.hoisted(() => ({
  getGpuClock: vi.fn(),
  setGpuClock: vi.fn(),
  setGpuClockAuto: vi.fn(),
  setGpuFollowGlobal: vi.fn(),
}));

vi.mock("../api", () => ({
  getGpuClock: mocks.getGpuClock,
  setGpuClock: mocks.setGpuClock,
  setGpuClockAuto: mocks.setGpuClockAuto,
  setGpuFollowGlobal: mocks.setGpuFollowGlobal,
}));

vi.mock("../tdp/useRunningGame", () => ({
  useRunningGame: () => runningGame,
}));

import { useGpuClock } from "./useGpuClock";

async function settle(): Promise<void> {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((onResolve, onReject) => {
    resolve = onResolve;
    reject = onReject;
  });
  return { promise, resolve, reject };
}

describe("useGpuClock System scope", () => {
  beforeEach(() => {
    runningGame = { appid: "42", liveAppid: 42, name: "Game" };
    mocks.getGpuClock.mockResolvedValue(GPU_STATE);
    mocks.setGpuClock.mockResolvedValue({ ...GPU_STATE, manual: true });
    mocks.setGpuClockAuto.mockResolvedValue(GPU_STATE);
    mocks.setGpuFollowGlobal.mockResolvedValue({
      ...GPU_STATE,
      follows_global: false,
      has_game_profile: true,
    });
  });

  afterEach(() => vi.clearAllMocks());

  it("owns its per-game selector without depending on the Power section", async () => {
    const { result } = renderHook(() => useGpuClock());
    await settle();

    expect(result.current.scope).toBe("global");
    act(() => result.current.onScope("game"));
    await settle();

    expect(mocks.setGpuFollowGlobal).toHaveBeenCalledWith(false, "42");
    act(() => result.current.setManual(true));
    await settle();
    expect(mocks.setGpuClock).toHaveBeenCalledWith(200, 2_700, "game", "42", "42");
  });

  it("cancels a queued manual window when the user returns to Auto", async () => {
    vi.useFakeTimers();
    mocks.getGpuClock.mockResolvedValue({ ...GPU_STATE, manual: true });
    const { result } = renderHook(() => useGpuClock());
    await settle();

    act(() => result.current.setWindow(800, 2_000));
    act(() => result.current.setManual(false));
    await settle();
    await act(async () => vi.advanceTimersByTimeAsync(200));

    expect(mocks.setGpuClockAuto).toHaveBeenCalledTimes(1);
    expect(mocks.setGpuClock).not.toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("tags a global write with the game context that created it", async () => {
    const { result } = renderHook(() => useGpuClock());
    await settle();

    act(() => result.current.setManual(true));
    await settle();

    expect(mocks.setGpuClock).toHaveBeenCalledWith(200, 2_700, "global", null, "42");
  });

  it("restores confirmed state when enabling Manual is rejected", async () => {
    mocks.setGpuClock.mockRejectedValueOnce(new Error("transport"));
    const { result } = renderHook(() => useGpuClock());
    await settle();

    act(() => result.current.setManual(true));
    await settle();

    expect(result.current.state?.manual).toBe(false);
  });

  it("ignores a GPU state response from the previous game", async () => {
    const first = deferred<GpuClockState>();
    const second = deferred<GpuClockState>();
    mocks.getGpuClock
      .mockReset()
      .mockImplementationOnce(() => first.promise)
      .mockImplementationOnce(() => second.promise)
      .mockResolvedValue({ ...GPU_STATE, min: 900 });
    runningGame = { appid: "100", liveAppid: 100, name: "First" };
    const { result, rerender } = renderHook(() => useGpuClock());

    runningGame = { appid: "200", liveAppid: 200, name: "Second" };
    rerender();
    second.resolve({ ...GPU_STATE, min: 900 });
    await settle();
    first.resolve({ ...GPU_STATE, min: 500 });
    await settle();

    expect(result.current.state?.min).toBe(900);
  });

  it("keeps a slow scope mutation authoritative over its stale refresh", async () => {
    const follow = deferred<GpuClockState>();
    mocks.setGpuFollowGlobal.mockImplementationOnce(() => follow.promise);
    const { result } = renderHook(() => useGpuClock());
    await settle();

    act(() => result.current.onScope("game"));
    await settle();
    follow.resolve({
      ...GPU_STATE,
      follows_global: false,
      has_game_profile: true,
    });
    await settle();

    expect(result.current.scope).toBe("game");
    expect(result.current.state?.follows_global).toBe(false);
  });

  it("restores the confirmed scope when its mutation is rejected", async () => {
    mocks.setGpuFollowGlobal.mockRejectedValueOnce(new Error("transport"));
    const { result } = renderHook(() => useGpuClock());
    await settle();

    act(() => result.current.onScope("game"));
    await settle();

    expect(result.current.scope).toBe("global");
    expect(result.current.state?.follows_global).toBe(true);
  });

  it("invalidates an in-flight GPU mutation when the running game changes", async () => {
    const stale = deferred<GpuClockState>();
    mocks.setGpuClock.mockImplementationOnce(() => stale.promise);
    mocks.getGpuClock.mockImplementation(async () => ({
      ...GPU_STATE,
      min: runningGame?.appid === "200" ? 900 : 700,
    }));
    runningGame = { appid: "100", liveAppid: 100, name: "First" };
    const { result, rerender } = renderHook(() => useGpuClock());
    await settle();

    act(() => result.current.setManual(true));
    runningGame = { appid: "200", liveAppid: 200, name: "Second" };
    rerender();
    await settle();
    stale.resolve({ ...GPU_STATE, manual: true, min: 500 });
    await settle();

    expect(result.current.state?.min).toBe(900);
    expect(result.current.state?.manual).toBe(false);
  });
});
