// @vitest-environment happy-dom
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CpuState } from "../api";
import type { RunningGame } from "../tdp/useRunningGame";

let runningGame: RunningGame | null = { appid: "100", liveAppid: 100, name: "First" };

const CPU_STATE: CpuState = {
  chip: "test",
  cores: 4,
  threads: 8,
  base_khz: 1_000_000,
  max_khz: 4_000_000,
  smt: { supported: true, enabled: true },
  boost: { supported: true, enabled: true },
  cores_supported: true,
  max_cores: 4,
  active_cores: 4,
  frequency: {
    supported: true,
    backend: "test",
    manual: false,
    range_min_khz: 1_000_000,
    range_max_khz: 4_000_000,
    requested_min_khz: null,
    requested_max_khz: null,
    applied_min_khz: 1_000_000,
    applied_max_khz: 4_000_000,
    status: "automatic",
    reason: null,
    epoch: 1,
    policy_state: [],
  },
  follows_global: true,
  has_game_profile: false,
};

const mocks = vi.hoisted(() => ({
  getCpuState: vi.fn(),
  setCpuFollowGlobal: vi.fn(),
  setCpuFrequency: vi.fn(),
  setCpuFrequencyAuto: vi.fn(),
}));

vi.mock("../api", () => ({
  getCpuState: mocks.getCpuState,
  setActiveCores: vi.fn(async () => CPU_STATE),
  setCpuBoost: vi.fn(async () => CPU_STATE),
  setCpuFollowGlobal: mocks.setCpuFollowGlobal,
  setCpuFrequency: mocks.setCpuFrequency,
  setCpuFrequencyAuto: mocks.setCpuFrequencyAuto,
  setSmt: vi.fn(async () => CPU_STATE),
}));

vi.mock("../tdp/useRunningGame", () => ({
  useRunningGame: () => runningGame,
}));

import { useCpu } from "./useCpu";

async function settlePromises(): Promise<void> {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((onResolve) => {
    resolve = onResolve;
  });
  return { promise, resolve };
}

describe("useCpu polling", () => {
  beforeEach(() => {
    runningGame = { appid: "100", liveAppid: 100, name: "First" };
    mocks.getCpuState.mockImplementation(async () => ({
      ...CPU_STATE,
      chip: runningGame?.appid ?? "none",
    }));
    mocks.setCpuFrequency.mockResolvedValue(CPU_STATE);
    mocks.setCpuFrequencyAuto.mockResolvedValue(CPU_STATE);
    mocks.setCpuFollowGlobal.mockResolvedValue(CPU_STATE);
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("keeps polling after a queued frequency change is cancelled by a game change", async () => {
    const { result, rerender } = renderHook(() => useCpu());
    await settlePromises();
    expect(mocks.getCpuState).toHaveBeenCalledTimes(1);
    expect(result.current.state?.chip).toBe("100");

    act(() => result.current.setFrequency(1_500_000, 3_000_000));
    runningGame = { appid: "200", liveAppid: 200, name: "Second" };
    rerender();
    await settlePromises();
    expect(mocks.setCpuFrequency).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3_000);
    });

    expect(mocks.getCpuState).toHaveBeenCalledTimes(3);
    expect(result.current.state?.chip).toBe("200");
  });

  it("does not let a poll clobber a frequency change waiting for its debounce", async () => {
    const { result } = renderHook(() => useCpu());
    await settlePromises();

    act(() => {
      vi.advanceTimersByTime(2_950);
    });
    act(() => result.current.setFrequency(1_500_000, 3_000_000));
    expect(result.current.state?.frequency.requested_min_khz).toBe(1_500_000);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    });

    expect(result.current.state?.frequency.requested_min_khz).toBe(1_500_000);
    expect(mocks.setCpuFrequency).not.toHaveBeenCalled();
  });

  it("cancels a queued manual window when frequency control returns to automatic", async () => {
    const { result } = renderHook(() => useCpu());
    await settlePromises();

    act(() => result.current.setFrequency(1_500_000, 3_000_000));
    act(() => result.current.setFrequencyManual(false));
    await settlePromises();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(200);
    });

    expect(mocks.setCpuFrequencyAuto).toHaveBeenCalledTimes(1);
    expect(mocks.setCpuFrequency).not.toHaveBeenCalled();
  });

  it("tags a global frequency write with the game context that created it", async () => {
    const { result } = renderHook(() => useCpu());
    await settlePromises();

    act(() => result.current.setFrequency(1_500_000, 3_000_000));
    await act(async () => vi.advanceTimersByTimeAsync(200));

    expect(mocks.setCpuFrequency).toHaveBeenCalledWith(
      1_500_000, 3_000_000, "global", null, "100",
    );
  });

  it("ignores a CPU mutation response from the previous game", async () => {
    const stale = deferred<CpuState>();
    mocks.setCpuFrequencyAuto.mockImplementationOnce(() => stale.promise);
    mocks.getCpuState.mockImplementation(async () => ({
      ...CPU_STATE,
      chip: runningGame?.appid ?? "none",
      frequency: { ...CPU_STATE.frequency, manual: true },
    }));
    const { result, rerender } = renderHook(() => useCpu());
    await settlePromises();

    act(() => result.current.setFrequencyManual(false));
    runningGame = { appid: "200", liveAppid: 200, name: "Second" };
    rerender();
    await settlePromises();
    stale.resolve({ ...CPU_STATE, chip: "100" });
    await settlePromises();

    expect(result.current.state?.chip).toBe("200");
  });

  it("resumes polling after a mutation settles in the current game", async () => {
    const { result } = renderHook(() => useCpu());
    await settlePromises();

    act(() => result.current.setFrequencyManual(false));
    await settlePromises();
    await act(async () => vi.advanceTimersByTimeAsync(3_000));

    expect(mocks.getCpuState).toHaveBeenCalledTimes(2);
    expect(result.current.state?.chip).toBe("100");
  });

  it("restores the confirmed scope when its mutation is rejected", async () => {
    mocks.setCpuFollowGlobal.mockRejectedValueOnce(new Error("transport"));
    const { result } = renderHook(() => useCpu());
    await settlePromises();

    act(() => result.current.onScope("game"));
    await settlePromises();

    expect(result.current.scope).toBe("global");
    expect(result.current.state?.follows_global).toBe(true);
  });
});
