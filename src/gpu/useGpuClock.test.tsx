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
    expect(mocks.setGpuClock).toHaveBeenCalledWith(200, 2_700, "game", "42");
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
});
