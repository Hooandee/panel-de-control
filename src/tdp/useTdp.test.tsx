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
  on_ac: false,
  auto_limits: { min: 5, default: 15, max: 25, max_ac: 40 },
  auto_request_limits: { min: 5, default: 15, max: 35, max_ac: 40 },
  watts: 15,
  global_watts: 15,
  levels: { pl1: 15, pl2: 15, pl3: 15 },
  global_levels: { pl1: 15, pl2: 15, pl3: 15 },
  requested_levels: { pl1: 15, pl2: 15, pl3: 15 },
  global_requested_levels: { pl1: 15, pl2: 15, pl3: 15 },
  boost_mode: "estable",
  global_boost_mode: "estable",
  auto_config: { enabled: false, target_fps: 40, initial_tdp: 15, min_tdp: null, max_tdp: null },
  global_auto_config: { enabled: false, target_fps: 40, initial_tdp: 15, min_tdp: null, max_tdp: null },
  seen_autotdp_notice: true,
};

const mocks = vi.hoisted(() => ({
  getTdpState: vi.fn(),
  getPowerDraw: vi.fn(),
  getPowerPresets: vi.fn(),
  setTdpWatts: vi.fn(),
  setTdpLevels: vi.fn(),
  setTdpFollowGlobal: vi.fn(),
  setLowBatteryTdpHold: vi.fn(),
  setAutoTdp: vi.fn(),
  setAutoTdpConfig: vi.fn(),
  notifyLearningStatusChanged: vi.fn(),
}));

vi.mock("../api", () => ({
  getTdpState: mocks.getTdpState,
  getPowerDraw: mocks.getPowerDraw,
  getPowerPresets: mocks.getPowerPresets,
  setTdpWatts: mocks.setTdpWatts,
  setTdpLevels: mocks.setTdpLevels,
  setTdpFollowGlobal: mocks.setTdpFollowGlobal,
  setLowBatteryTdpHold: mocks.setLowBatteryTdpHold,
  setTdpBoostMode: vi.fn(async () => TDP_STATE),
  setTdpFirmwareMode: vi.fn(async () => TDP_STATE),
  setAutoTdp: mocks.setAutoTdp,
  setAutoTdpConfig: mocks.setAutoTdpConfig,
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

vi.mock("../learning/statusInvalidation", () => ({
  notifyLearningStatusChanged: mocks.notifyLearningStatusChanged,
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
    mocks.setLowBatteryTdpHold.mockResolvedValue(TDP_STATE);
    mocks.setAutoTdp.mockResolvedValue({ auto_tdp: false });
    mocks.setAutoTdpConfig.mockResolvedValue(TDP_STATE);
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

  it("keeps requested boost rails in sync during an optimistic level edit", async () => {
    const { result } = renderHook(() => useTdp());
    await settle();

    act(() => result.current.onSetLevels(2, 3));

    expect(result.current.tdp?.global_requested_levels).toEqual({
      pl1: 15,
      pl2: 17,
      pl3: 20,
    });
    expect(result.current.tdp?.global_levels).toEqual({
      pl1: 15,
      pl2: 15,
      pl3: 15,
    });
  });

  it("updates global AutoTDP settings optimistically and writes them with game context", async () => {
    const { result } = renderHook(() => useTdp());
    await settle();

    act(() => result.current.onAutoTargetFps(57));
    expect(result.current.tdp?.global_auto_config).toEqual({
      enabled: false,
      target_fps: 57,
      initial_tdp: 15,
      min_tdp: null,
      max_tdp: null,
    });
    await act(async () => vi.advanceTimersByTimeAsync(200));

    expect(mocks.setAutoTdpConfig).toHaveBeenCalledWith(
      57,
      15,
      "global",
      null,
      "100",
      null,
      null,
    );
  });

  it.each([
    { endpoint: "min" as const, watts: 22, minimum: 22, maximum: 22, initial: 22 },
    { endpoint: "max" as const, watts: 8, minimum: 8, maximum: 8, initial: 8 },
  ])("moves both endpoints and the initial TDP atomically when $endpoint crosses", async ({ endpoint, watts, minimum, maximum, initial }) => {
    mocks.getTdpState.mockResolvedValue({
      ...TDP_STATE,
      global_auto_config: { ...TDP_STATE.global_auto_config, min_tdp: 10, max_tdp: 20 },
    });
    const { result } = renderHook(() => useTdp());
    await settle();
    act(() => endpoint === "min" ? result.current.onAutoMinTdp(watts) : result.current.onAutoMaxTdp(watts));
    expect(result.current.tdp?.global_auto_config).toMatchObject({ min_tdp: minimum, max_tdp: maximum, initial_tdp: initial });
    await act(async () => vi.advanceTimersByTimeAsync(200));
    expect(mocks.setAutoTdpConfig).toHaveBeenCalledExactlyOnceWith(40, initial, "global", null, "100", minimum, maximum);
  });

  it("preserves a charger-capable requested range while clamping the initial TDP on battery", async () => {
    const { result } = renderHook(() => useTdp());
    await settle();
    act(() => result.current.onAutoMinTdp(30));
    expect(result.current.tdp?.global_auto_config).toMatchObject({ min_tdp: 30, max_tdp: null, initial_tdp: 25 });
    await act(async () => vi.advanceTimersByTimeAsync(200));
    expect(mocks.setAutoTdpConfig).toHaveBeenCalledExactlyOnceWith(40, 25, "global", null, "100", 30, null);
  });

  it("preserves explicit endpoints when only FPS changes", async () => {
    mocks.getTdpState.mockResolvedValue({
      ...TDP_STATE,
      global_auto_config: { ...TDP_STATE.global_auto_config, min_tdp: 10, max_tdp: 40 },
    });
    const { result } = renderHook(() => useTdp());
    await settle();
    act(() => result.current.onAutoTargetFps(57));
    await act(async () => vi.advanceTimersByTimeAsync(200));
    expect(mocks.setAutoTdpConfig).toHaveBeenCalledExactlyOnceWith(57, 15, "global", null, "100", 10, 40);
  });

  it("keeps range and FPS edits made before React publishes the optimistic state", async () => {
    const { result } = renderHook(() => useTdp());
    await settle();
    act(() => {
      result.current.onAutoMinTdp(10);
      result.current.onAutoMaxTdp(20);
      result.current.onAutoTargetFps(57);
    });
    expect(result.current.tdp?.global_auto_config).toMatchObject({ min_tdp: 10, max_tdp: 20, target_fps: 57 });
    await act(async () => vi.advanceTimersByTimeAsync(200));
    expect(mocks.setAutoTdpConfig).toHaveBeenCalledExactlyOnceWith(57, 15, "global", null, "100", 10, 20);
  });

  it("cancels a pending Auto range edit when the running game changes", async () => {
    const { result, rerender } = renderHook(() => useTdp());
    await settle();
    act(() => result.current.onAutoMinTdp(20));
    runningGame = { appid: "200", liveAppid: 200, name: "Second" };
    rerender();
    await settle();
    act(() => result.current.onAutoTargetFps(57));
    await act(async () => vi.advanceTimersByTimeAsync(200));
    expect(mocks.setAutoTdpConfig).toHaveBeenCalledExactlyOnceWith(57, 15, "global", null, "200", null, null);
  });

  it("does not let an older Auto write response replace newer range intent", async () => {
    let finishFirst!: (value: typeof TDP_STATE) => void;
    mocks.setAutoTdpConfig.mockImplementationOnce(() => new Promise((resolve) => { finishFirst = resolve; }));
    const { result } = renderHook(() => useTdp());
    await settle();
    act(() => result.current.onAutoMinTdp(10));
    await act(async () => vi.advanceTimersByTimeAsync(200));
    act(() => result.current.onAutoMaxTdp(20));
    await act(async () => finishFirst(TDP_STATE));
    expect(result.current.tdp?.global_auto_config).toMatchObject({ min_tdp: 10, max_tdp: 20 });
    await act(async () => vi.advanceTimersByTimeAsync(200));
    expect(mocks.setAutoTdpConfig).toHaveBeenLastCalledWith(40, 15, "global", null, "100", 10, 20);
  });

  it.each([
    ["scope", "global", "game"],
    ["game", "scope", "global"],
    ["game", "global", "scope"],
    ["game", "global", "refresh", "scope"],
  ])("persists both scopes and preserves newer intent with response order %s → %s → %s", async (...order) => {
    const responses: Record<string, () => void> = {};
    const globalConfig = { ...TDP_STATE.global_auto_config, min_tdp: 10 };
    const gameConfig = { ...TDP_STATE.auto_config, target_fps: 60, max_tdp: 20 };
    mocks.getTdpState.mockResolvedValue({ ...TDP_STATE, follows_global: false });
    mocks.setTdpFollowGlobal.mockImplementation((follow) => follow ? Promise.resolve(TDP_STATE) : new Promise((resolve) => {
      responses.scope = () => resolve({ ...TDP_STATE, follows_global: false });
    }));
    mocks.setAutoTdpConfig.mockImplementation((_fps, _initial, scope) => new Promise((resolve) => {
      responses[scope] = () => resolve(scope === "global"
        ? { ...TDP_STATE, global_auto_config: globalConfig }
        : { ...TDP_STATE, follows_global: false, auto_config: gameConfig });
    }));
    const { result } = renderHook(() => useTdp());
    await settle();
    act(() => result.current.onScope("global"));
    await settle();
    act(() => result.current.onAutoMinTdp(10));
    act(() => result.current.onScope("game"));
    act(() => {
      result.current.onAutoMaxTdp(20);
      result.current.onAutoTargetFps(60);
    });
    await act(async () => vi.advanceTimersByTimeAsync(200));
    expect(mocks.setAutoTdpConfig).toHaveBeenCalledTimes(2);
    expect(mocks.setAutoTdpConfig).toHaveBeenCalledWith(40, 15, "global", null, "100", 10, null);
    expect(mocks.setAutoTdpConfig).toHaveBeenCalledWith(60, 15, "game", "100", "100", null, 20);
    responses.refresh = () => {
      mocks.getTdpState.mockResolvedValue({
        ...TDP_STATE, follows_global: false, global_auto_config: globalConfig, auto_config: gameConfig,
      });
      result.current.refresh();
    };
    for (const response of order) {
      await act(async () => responses[response]());
      expect(result.current.tdp?.global_auto_config).toEqual(globalConfig);
      expect(result.current.tdp?.auto_config).toEqual(result.current.tdp?.follows_global ? globalConfig : gameConfig);
      expect(result.current.scope).toBe("game");
    }
  });

  it("preserves a durable 35 W start on an FPS-only battery edit and charger return", async () => {
    const config = { ...TDP_STATE.global_auto_config, initial_tdp: 35 };
    mocks.getTdpState.mockResolvedValue({ ...TDP_STATE, global_auto_config: config });
    mocks.setAutoTdpConfig.mockImplementation(async (fps, initial) => ({
      ...TDP_STATE, global_auto_config: { ...config, target_fps: fps, initial_tdp: initial },
    }));
    const { result } = renderHook(() => useTdp());
    await settle();
    act(() => result.current.onAutoTargetFps(57));
    expect(result.current.tdp?.global_auto_config.initial_tdp).toBe(35);
    await act(async () => vi.advanceTimersByTimeAsync(200));
    expect(mocks.setAutoTdpConfig).toHaveBeenCalledExactlyOnceWith(57, 35, "global", null, "100", null, null);
    mocks.getTdpState.mockResolvedValue({ ...TDP_STATE, on_ac: true, global_auto_config: { ...config, target_fps: 57 } });
    mocks.getPowerDraw.mockResolvedValue({ on_ac: true, ownership: {} });
    await act(async () => vi.advanceTimersByTimeAsync(1000));
    expect(result.current.tdp?.on_ac).toBe(true);
    expect(result.current.tdp?.global_auto_config.initial_tdp).toBe(35);
  });

  it.each([false, true])("keeps own-game identity through inherited global state (late game response: %s)", async (lateGameResponse) => {
    let follows = false;
    let own = { ...TDP_STATE.auto_config, initial_tdp: 12, max_tdp: 20 as number | null };
    let global = { ...TDP_STATE.global_auto_config, initial_tdp: 25, max_tdp: 35 as number | null };
    const state = () => ({ ...TDP_STATE, follows_global: follows, auto_config: follows ? global : own, global_auto_config: global });
    let finishGame!: () => void;
    let finishFollow!: () => void;
    let gameWrites = 0;
    mocks.getTdpState.mockImplementation(async () => state());
    mocks.setTdpFollowGlobal.mockImplementation((follow) => {
      if (follow) {
        follows = true;
        return Promise.resolve(state());
      }
      return new Promise((resolve) => {
        finishFollow = () => { follows = false; resolve(state()); };
      });
    });
    mocks.setAutoTdpConfig.mockImplementation((fps, initial, sc, _target, _context, _minimum, maximum) => {
      if (sc === "global") {
        global = { ...global, target_fps: fps, initial_tdp: initial, max_tdp: maximum };
      } else {
        own = { ...own, target_fps: fps, initial_tdp: initial, max_tdp: maximum };
        gameWrites += 1;
        if (gameWrites === 1 && lateGameResponse) {
          return new Promise((resolve) => { finishGame = () => resolve(state()); });
        }
      }
      return Promise.resolve(state());
    });
    const { result } = renderHook(() => useTdp());
    await settle();
    expect(result.current.scope).toBe("game");
    act(() => result.current.onAutoMaxTdp(20));
    await act(async () => vi.advanceTimersByTimeAsync(200));
    act(() => result.current.onScope("global"));
    await settle();
    act(() => result.current.onAutoMaxTdp(40));
    await act(async () => vi.advanceTimersByTimeAsync(200));
    if (lateGameResponse) await act(async () => finishGame());
    act(() => result.current.refresh());
    await settle();
    expect(result.current.tdp?.auto_config).toEqual(global);
    act(() => result.current.onScope("game"));
    act(() => result.current.onAutoTargetFps(57));
    await act(async () => vi.advanceTimersByTimeAsync(200));
    expect(mocks.setAutoTdpConfig).toHaveBeenLastCalledWith(57, 12, "game", "100", "100", null, 20);
    expect(result.current.tdp?.auto_config).toEqual(global);
    await act(async () => finishFollow());
    expect(result.current.tdp?.auto_config).toMatchObject({ target_fps: 57, initial_tdp: 12, max_tdp: 20 });
    expect(result.current.tdp?.global_auto_config).toMatchObject({ initial_tdp: 25, max_tdp: 40 });
  });

  it("toggles the selected global config even if live power belongs to a game", async () => {
    const { result } = renderHook(() => useTdp());
    await settle();

    act(() => result.current.onAutoTdpToggle(true));
    await settle();

    expect(mocks.setAutoTdp).toHaveBeenCalledWith(
      true,
      "global",
      null,
      "100",
    );
    expect(mocks.notifyLearningStatusChanged).toHaveBeenCalledOnce();
  });

  it("moves requested custom boost rails with an optimistic watts edit", async () => {
    mocks.getTdpState.mockResolvedValue({
      ...TDP_STATE,
      global_boost_mode: "custom",
      global_requested_levels: { pl1: 15, pl2: 17, pl3: 20 },
    });
    const { result } = renderHook(() => useTdp());
    await settle();

    act(() => result.current.onWatts(10));

    expect(result.current.tdp?.global_watts).toBe(10);
    expect(result.current.tdp?.global_requested_levels).toEqual({
      pl1: 10,
      pl2: 12,
      pl3: 15,
    });
    expect(result.current.tdp?.global_levels).toEqual({
      pl1: 15,
      pl2: 15,
      pl3: 15,
    });
  });

  it("backs off long enough to recover capabilities published after ten seconds", async () => {
    const availableAt = Date.now() + 10_000;
    mocks.getTdpState.mockImplementation(async () => ({
      ...TDP_STATE,
      supported: Date.now() >= availableAt,
      recovery_pending: Date.now() < availableAt,
    }));

    const { result } = renderHook(() => useTdp());
    await settle();

    expect(result.current.tdp?.recovery_pending).toBe(true);

    await act(async () => vi.advanceTimersByTimeAsync(14_000));
    await settle();

    expect(result.current.tdp?.supported).toBe(true);
    expect(result.current.tdp?.recovery_pending).toBe(false);
    expect(mocks.getTdpState).toHaveBeenCalledTimes(4);
  });

  it("updates the low-battery hold from the backend response", async () => {
    mocks.setLowBatteryTdpHold.mockResolvedValue({
      ...TDP_STATE,
      low_battery_hold: {
        available: true,
        enabled: true,
        active: false,
        verified: false,
        status: "inactive",
        applied_w: null,
        reason: "battery_above_threshold",
      },
    });
    const { result } = renderHook(() => useTdp());
    await settle();

    await act(async () => result.current.onLowBatteryHold(true));

    expect(mocks.setLowBatteryTdpHold).toHaveBeenCalledWith(true);
    expect(result.current.tdp?.low_battery_hold.enabled).toBe(true);
  });

});
