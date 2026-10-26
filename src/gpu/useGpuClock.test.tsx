// @vitest-environment happy-dom
import { notifyPowerOwnershipChanged } from "../tdp/powerOwnershipInvalidation";
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { GpuClockState } from "../api";
import type { RunningGame } from "../tdp/useRunningGame";

const ownershipUi = vi.hoisted(() => ({ modal: null as any }));
vi.mock("@decky/ui", () => ({ Router: {}, findModuleByExport: () => undefined, findModuleExport: () => undefined }));
vi.mock("../navigation/showModal", () => ({ showModal: (element: any) => { ownershipUi.modal = element; } }));
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

  it("keeps the completed global reset when older same-revision reads finish later", async () => {
    runningGame = null;
    const owner = { supported: true, context_appid: null, revision: 1, observed: true,
      steam_profile: "inactive" as const, explicit_owner: null, owner: "pdc" as const,
      write_allowed: true, reason: "global" };
    const reads: Array<(state: any) => void> = [];
    mocks.getGpuClock.mockImplementation(() => new Promise((resolve) => reads.push(resolve)));
    const { result } = renderHook(() => useGpuClock());
    act(() => notifyPowerOwnershipChanged({ ...owner }));
    act(() => notifyPowerOwnershipChanged({ ...owner }));
    reads[2]({ ...GPU_STATE, manual: false, min: 200, game_power_owner: { ...owner } });
    await settle();
    expect(result.current.state?.manual).toBe(false);
    reads[1]({ ...GPU_STATE, manual: true, min: 1200, game_power_owner: { ...owner } });
    reads[0]({ ...GPU_STATE, manual: true, min: 1200, game_power_owner: { ...owner } });
    await settle();
    expect(result.current.state?.manual).toBe(false);
    expect(result.current.state?.min).toBe(200);
  });

  it("refreshes the effective baseline after a handoff and ignores obsolete ownership responses", async () => {
    const owner = { supported: true, context_appid: "42", revision: 1, observed: true,
      steam_profile: "active" as const, explicit_owner: "steam" as const, owner: "steam" as const,
      write_allowed: false, reason: "explicit" };
    mocks.getGpuClock.mockResolvedValue({ ...GPU_STATE, game_power_owner: owner });
    const { result } = renderHook(() => useGpuClock());
    await settle();
    let complete!: (state: any) => void;
    mocks.getGpuClock.mockImplementationOnce(() => new Promise((resolve) => { complete = resolve; }));
    act(() => notifyPowerOwnershipChanged({ ...owner, revision: 2 }));
    const latest = { ...owner, revision: 3, explicit_owner: "pdc" as const, owner: "pdc" as const, write_allowed: true };
    mocks.getGpuClock.mockResolvedValue({ ...GPU_STATE, min: 850, game_power_owner: latest });
    act(() => notifyPowerOwnershipChanged(latest));
    await settle();
    expect(result.current.state?.min).toBe(850);
    complete({ ...GPU_STATE, game_power_owner: { ...owner, revision: 2 } });
    await settle();
    act(() => notifyPowerOwnershipChanged({ ...owner, context_appid: "other", revision: 99 }));
    expect(result.current.state?.game_power_owner?.revision).toBe(3);
    expect(result.current.state?.game_power_owner?.owner).toBe("pdc");
  });

  it("updates all mounted cards after another card changes ownership without replacing a draft", async () => {
    vi.useFakeTimers();
    const owner = { supported: true, context_appid: "42", revision: 1, observed: true,
      steam_profile: "active" as const, explicit_owner: "pdc" as const, owner: "pdc" as const,
      write_allowed: true, reason: "explicit" };
    mocks.getGpuClock.mockResolvedValue({ ...GPU_STATE, game_power_owner: owner });
    const first = renderHook(() => useGpuClock());
    const second = renderHook(() => useGpuClock());
    await settle();
    act(() => first.result.current.setWindow(800, 1200));
    const changed = { ...owner, revision: 2, explicit_owner: "steam" as const, owner: "steam" as const, write_allowed: false };
    act(() => notifyPowerOwnershipChanged(changed));
    await settle();
    expect(first.result.current.state?.game_power_owner?.revision).toBe(2);
    expect(second.result.current.state?.game_power_owner?.owner).toBe("steam");
    expect(first.result.current.state?.min).toBe(800);
    first.unmount(); second.unmount();
    vi.useRealTimers();
  });

  it("leaves the GPU window and debounce untouched while confirmation is pending", async () => {
    vi.useFakeTimers();
    mocks.getGpuClock.mockResolvedValue({ ...GPU_STATE, game_power_owner: {
      context_appid: "42", revision: 1, observed: true, steam_profile: "active", explicit_owner: null, owner: "steam",
    } });
    const {result} = renderHook(() => useGpuClock());
    await settle();
    act(() => result.current.onScope("game")); await settle();
    act(() => result.current.setWindow(900, 1200));
    expect(ownershipUi.modal).not.toBeNull();
    expect(result.current.state?.min).toBe(200);
    await act(async () => vi.advanceTimersByTimeAsync(300));
    expect(mocks.setGpuClock).not.toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("selects the saved game profile when a game appears after mounting", async () => {
    runningGame = null;
    const { result, rerender } = renderHook(() => useGpuClock());
    await settle();
    expect(result.current.scope).toBe("global");
    mocks.getGpuClock.mockResolvedValue({ ...GPU_STATE, appid: "42", follows_global: false, min: 800 });
    runningGame = { appid: "42", liveAppid: 42, name: "Game" };
    rerender();
    await settle();
    expect(result.current.scope).toBe("game");
    expect(result.current.state?.min).toBe(800);
    expect(mocks.setGpuFollowGlobal).not.toHaveBeenCalled();
  });

  it("owns its per-game selector without depending on the Power section", async () => {
    const { result } = renderHook(() => useGpuClock());
    await settle();

    expect(result.current.scope).toBe("global");
    act(() => result.current.onScope("game"));
    await settle();

    expect(mocks.setGpuFollowGlobal).not.toHaveBeenCalled();
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

  it("switches views without creating or resetting a GPU profile", async () => {
    mocks.getGpuClock.mockResolvedValue({ ...GPU_STATE, appid: "42", follows_global: false,
      manual: true, min: 900, max: 1200, global_manual: false, global_min: 200, global_max: 2700 });
    const { result } = renderHook(() => useGpuClock());
    await settle();
    expect(result.current.scope).toBe("game");
    expect(result.current.state?.min).toBe(900);
    act(() => result.current.onScope("global")); await settle();
    expect(result.current.state?.manual).toBe(false);
    expect(result.current.state?.min).toBe(200);
    act(() => result.current.onScope("game")); await settle();
    expect(result.current.state?.min).toBe(900);
    expect(mocks.setGpuFollowGlobal).not.toHaveBeenCalled();
    expect(mocks.setGpuClock).not.toHaveBeenCalled();
    expect(mocks.setGpuClockAuto).not.toHaveBeenCalled();
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
