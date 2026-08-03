// @vitest-environment happy-dom
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { RunningGame } from "./useRunningGame";

let runningGame: RunningGame | null = {
  appid: "100",
  liveAppid: 100,
  name: "First",
};

const TDP_STATE = {
  follows_global: true,
  watts: 15,
  global_watts: 15,
  levels: { pl1: 15, pl2: 15, pl3: 15 },
  global_levels: { pl1: 15, pl2: 15, pl3: 15 },
  boost_mode: "estable",
  global_boost_mode: "estable",
  seen_autotdp_notice: true,
};

const mocks = vi.hoisted(() => ({
  getTdpState: vi.fn(),
  getPowerDraw: vi.fn(),
  getPowerPresets: vi.fn(),
  setTdpWatts: vi.fn(),
  setTdpLevels: vi.fn(),
  setTdpFollowGlobal: vi.fn(),
}));

vi.mock("../api", () => ({
  getTdpState: mocks.getTdpState,
  getPowerDraw: mocks.getPowerDraw,
  getPowerPresets: mocks.getPowerPresets,
  setTdpWatts: mocks.setTdpWatts,
  setTdpLevels: mocks.setTdpLevels,
  setTdpFollowGlobal: mocks.setTdpFollowGlobal,
  setTdpBoostMode: vi.fn(async () => TDP_STATE),
  setTdpFirmwareMode: vi.fn(async () => TDP_STATE),
  setAutoTdp: vi.fn(async () => ({ auto_tdp: false })),
  setSeenAutotdpNotice: vi.fn(async () => true),
  applyPowerPreset: vi.fn(async () => ({
    requested_w: 15,
    applied_w: 15,
    ok: true,
    detail: "",
  })),
}));

vi.mock("./useRunningGame", () => ({
  useRunningGame: () => runningGame,
}));

vi.mock("../components/AutoTdpNoticeModal", () => ({
  openAutoTdpNoticeModal: vi.fn(),
}));

import { useTdp } from "./useTdp";

async function settle(): Promise<void> {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("useTdp game context", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    runningGame = { appid: "100", liveAppid: 100, name: "First" };
    mocks.getTdpState.mockResolvedValue(TDP_STATE);
    mocks.getPowerDraw.mockResolvedValue({
      watts: 15,
      gpu_busy: 0,
      auto_tdp: false,
      setpoint: null,
      applied: 15,
      ui_floor_engaged: false,
      on_ac: false,
      ownership: {},
    });
    mocks.getPowerPresets.mockResolvedValue({
      order: [],
      hidden: [],
      custom: {},
    });
    mocks.setTdpWatts.mockResolvedValue({
      requested_w: 20,
      applied_w: 20,
      ok: true,
      detail: "",
    });
    mocks.setTdpLevels.mockResolvedValue({
      requested_w: 15,
      applied_w: 15,
      ok: true,
      detail: "",
    });
    mocks.setTdpFollowGlobal.mockResolvedValue(TDP_STATE);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("cancels queued watts and levels when the running game changes", async () => {
    const { result, rerender } = renderHook(() => useTdp());
    await settle();

    act(() => {
      result.current.onWatts(20);
      result.current.onSetLevels(2, 3);
    });
    runningGame = { appid: "200", liveAppid: 200, name: "Second" };
    rerender();
    await settle();
    await act(async () => vi.advanceTimersByTimeAsync(200));

    expect(mocks.setTdpWatts).not.toHaveBeenCalled();
    expect(mocks.setTdpLevels).not.toHaveBeenCalled();
  });

  it("tags a global watts write with the game context that created it", async () => {
    const { result } = renderHook(() => useTdp());
    await settle();

    act(() => result.current.onWatts(20));
    await act(async () => vi.advanceTimersByTimeAsync(200));

    expect(mocks.setTdpWatts).toHaveBeenCalledWith(
      20,
      "global",
      null,
      "100",
    );
  });
});
