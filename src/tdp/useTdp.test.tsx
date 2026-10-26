// @vitest-environment happy-dom
import { notifyPowerOwnershipChanged } from "../tdp/powerOwnershipInvalidation";
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { RunningGame } from "./useRunningGame";

const ownershipUi = vi.hoisted(() => ({ modal: null as any }));
vi.mock("@decky/ui", () => ({ Router: {}, findModuleByExport: () => undefined, findModuleExport: () => undefined }));
vi.mock("../navigation/showModal", () => ({ showModal: (element: any) => { ownershipUi.modal = element; } }));
let runningGame: RunningGame | null = {
  appid: "100",
  liveAppid: 100,
  name: "First",
};

const TDP_STATE = {
  appid: "100",
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

  it("refreshes a global reset after power polling and ignores its older same-revision start read", async () => {
    runningGame = null;
    const owner = { supported: true, context_appid: null, revision: 1, observed: true,
      steam_profile: "inactive" as const, explicit_owner: null, owner: "pdc" as const,
      write_allowed: true, reason: "global" };
    mocks.getTdpState.mockResolvedValue({ ...TDP_STATE, appid: null, watts: 12, global_watts: 12, game_power_owner: owner });
    const { result } = renderHook(() => useTdp());
    await settle();
    const reads: Array<(state: any) => void> = [];
    mocks.getTdpState.mockImplementation(() => new Promise((resolve) => reads.push(resolve)));
    act(() => notifyPowerOwnershipChanged({ ...owner }));
    act(() => notifyPowerOwnershipChanged({ ...owner }));
    await act(async () => vi.advanceTimersByTimeAsync(1000));
    reads[1]({ ...TDP_STATE, appid: null, watts: 15, global_watts: 15, game_power_owner: { ...owner } });
    await settle();
    expect(result.current.tdp?.global_watts).toBe(15);
    reads[0]({ ...TDP_STATE, appid: null, watts: 12, global_watts: 12, game_power_owner: { ...owner } });
    await settle();
    expect(result.current.tdp?.global_watts).toBe(15);
  });

  it("preserves a new watt draft entered while a reset read is pending", async () => {
    const owner = { supported: true, context_appid: "100", revision: 1, observed: true,
      steam_profile: "inactive" as const, explicit_owner: "pdc" as const, owner: "pdc" as const,
      write_allowed: true, reason: "explicit" };
    mocks.getTdpState.mockResolvedValue({ ...TDP_STATE, game_power_owner: owner });
    const { result } = renderHook(() => useTdp());
    await settle();
    let complete!: (state: any) => void;
    mocks.getTdpState.mockImplementationOnce(() => new Promise((resolve) => { complete = resolve; }));
    act(() => notifyPowerOwnershipChanged({ ...owner }));
    act(() => result.current.onWatts(22));
    complete({ ...TDP_STATE, global_watts: 15, game_power_owner: { ...owner } });
    await settle();
    expect(result.current.tdp?.global_watts).toBe(22);
  });

  it("refreshes the effective baseline after a handoff and ignores obsolete ownership responses", async () => {
    const owner = { supported: true, context_appid: "100", revision: 1, observed: true,
      steam_profile: "active" as const, explicit_owner: "steam" as const, owner: "steam" as const,
      write_allowed: false, reason: "explicit" };
    mocks.getTdpState.mockResolvedValue({ ...TDP_STATE, game_power_owner: owner });
    const { result } = renderHook(() => useTdp());
    await settle();
    let complete!: (state: any) => void;
    mocks.getTdpState.mockImplementationOnce(() => new Promise((resolve) => { complete = resolve; }));
    act(() => notifyPowerOwnershipChanged({ ...owner, revision: 2 }));
    const latest = { ...owner, revision: 3, explicit_owner: "pdc" as const, owner: "pdc" as const, write_allowed: true };
    mocks.getTdpState.mockResolvedValue({ ...TDP_STATE, watts: 11, game_power_owner: latest });
    act(() => notifyPowerOwnershipChanged(latest));
    await settle();
    expect(result.current.tdp?.watts).toBe(11);
    complete({ ...TDP_STATE, game_power_owner: { ...owner, revision: 2 } });
    await settle();
    act(() => notifyPowerOwnershipChanged({ ...owner, context_appid: "other", revision: 99 }));
    expect(result.current.tdp?.game_power_owner?.revision).toBe(3);
    expect(result.current.tdp?.game_power_owner?.owner).toBe("pdc");
  });

  it("updates all mounted cards after another card changes ownership without replacing a draft", async () => {
    vi.useFakeTimers();
    const owner = { supported: true, context_appid: "100", revision: 1, observed: true,
      steam_profile: "active" as const, explicit_owner: "pdc" as const, owner: "pdc" as const,
      write_allowed: true, reason: "explicit" };
    mocks.getTdpState.mockResolvedValue({ ...TDP_STATE, game_power_owner: owner });
    const first = renderHook(() => useTdp());
    const second = renderHook(() => useTdp());
    await settle();
    act(() => first.result.current.onWatts(22));
    const changed = { ...owner, revision: 2, explicit_owner: "steam" as const, owner: "steam" as const, write_allowed: false };
    act(() => notifyPowerOwnershipChanged(changed));
    await settle();
    expect(first.result.current.tdp?.game_power_owner?.revision).toBe(2);
    expect(second.result.current.tdp?.game_power_owner?.owner).toBe("steam");
    expect(first.result.current.tdp?.global_watts).toBe(22);
    first.unmount(); second.unmount();
    vi.useRealTimers();
  });

  it("leaves watts and debounce untouched until Steam ownership is confirmed", async () => {
    mocks.getTdpState.mockResolvedValue({ ...TDP_STATE, game_power_owner: {
      context_appid: "100", revision: 1, observed: true, steam_profile: "active", explicit_owner: null, owner: "steam",
    } });
    const {result} = renderHook(() => useTdp());
    await settle();
    act(() => result.current.onScope("game"));
    act(() => result.current.onWatts(22));
    expect(ownershipUi.modal).not.toBeNull();
    expect(result.current.tdp?.watts).toBe(15);
    await act(async () => vi.advanceTimersByTimeAsync(300));
    expect(mocks.setTdpWatts).not.toHaveBeenCalled();
  });

  it("switches views without writing profiles and routes explicit edits to the chosen scope", async () => {
    const { result } = renderHook(() => useTdp());
    await settle();
    act(() => result.current.onScope("game"));
    await settle();
    expect(result.current.scope).toBe("game");
    expect(mocks.setTdpFollowGlobal).not.toHaveBeenCalled();
    expect(mocks.setTdpWatts).not.toHaveBeenCalled();
    expect(mocks.setTdpLevels).not.toHaveBeenCalled();
    expect(mocks.setAutoTdp).not.toHaveBeenCalled();
    expect(mocks.setAutoTdpConfig).not.toHaveBeenCalled();
    expect(result.current.tdp?.follows_global).toBe(true);
    act(() => result.current.onWatts(18));
    await act(async () => vi.advanceTimersByTimeAsync(200));
    expect(mocks.setTdpWatts).toHaveBeenLastCalledWith(18, "game", "100", "100");
    expect(result.current.scope).toBe("game");
    act(() => result.current.onScope("global"));
    act(() => result.current.onWatts(20));
    await act(async () => vi.advanceTimersByTimeAsync(200));
    expect(mocks.setTdpWatts).toHaveBeenLastCalledWith(20, "global", null, "100");
    expect(mocks.setTdpFollowGlobal).not.toHaveBeenCalled();
  });

  it("initializes from the matching game profile without replacing an explicit view on refresh", async () => {
    mocks.getTdpState.mockResolvedValue({ ...TDP_STATE, follows_global: false });
    const { result } = renderHook(() => useTdp());
    await settle();
    expect(result.current.scope).toBe("game");
    act(() => result.current.onScope("global"));
    act(() => result.current.refresh());
    await settle();
    expect(result.current.scope).toBe("global");
    expect(result.current.tdp?.follows_global).toBe(false);
    expect(mocks.setTdpFollowGlobal).not.toHaveBeenCalled();
  });

  it("resets the local view for a new game and never exposes a game view without a game", async () => {
    const { result, rerender } = renderHook(() => useTdp());
    await settle();
    act(() => result.current.onScope("game"));
    runningGame = { appid: "200", liveAppid: 200, name: "Second" };
    rerender();
    await settle();
    expect(result.current.scope).toBe("global");
    runningGame = null;
    rerender();
    act(() => result.current.onScope("game"));
    expect(result.current.scope).toBe("global");
    expect(mocks.setTdpFollowGlobal).not.toHaveBeenCalled();
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
    { endpoint: "min" as const, watts: 22, minimum: 22, maximum: 22, initial: 15 },
    { endpoint: "max" as const, watts: 8, minimum: 8, maximum: 8, initial: 15 },
  ])("moves both endpoints and keeps the stored initial TDP when $endpoint crosses", async ({ endpoint, watts, minimum, maximum, initial }) => {
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

  it("preserves a charger-capable requested range and the stored initial TDP on battery", async () => {
    const { result } = renderHook(() => useTdp());
    await settle();
    act(() => result.current.onAutoMinTdp(30));
    expect(result.current.tdp?.global_auto_config).toMatchObject({ min_tdp: 30, max_tdp: null, initial_tdp: 15 });
    await act(async () => vi.advanceTimersByTimeAsync(200));
    expect(mocks.setAutoTdpConfig).toHaveBeenCalledExactlyOnceWith(40, 15, "global", null, "100", 30, null);
  });

  it("returns the initial TDP to the player's value when the range widens again", async () => {
    const { result } = renderHook(() => useTdp());
    await settle();
    act(() => result.current.onAutoMaxTdp(10));
    act(() => result.current.onAutoMaxTdp(30));
    expect(result.current.tdp?.global_auto_config.initial_tdp).toBe(15);
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
    ["global", "game"],
    ["game", "global"],
    ["game", "global", "refresh"],
  ])("persists both scopes and preserves newer intent with response order %s → %s → %s", async (...order) => {
    const responses: Record<string, () => void> = {};
    const globalConfig = { ...TDP_STATE.global_auto_config, min_tdp: 10 };
    const gameConfig = { ...TDP_STATE.auto_config, target_fps: 60, max_tdp: 20 };
    mocks.getTdpState.mockResolvedValue({ ...TDP_STATE, follows_global: false });
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
    const follows = false;
    let own = { ...TDP_STATE.auto_config, initial_tdp: 12, max_tdp: 20 as number | null };
    let global = { ...TDP_STATE.global_auto_config, initial_tdp: 25, max_tdp: 35 as number | null };
    const state = () => ({ ...TDP_STATE, follows_global: follows, auto_config: follows ? global : own, global_auto_config: global });
    let finishGame!: () => void;
    let gameWrites = 0;
    mocks.getTdpState.mockImplementation(async () => state());
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
    expect(result.current.tdp?.auto_config).toEqual(own);
    act(() => result.current.onScope("game"));
    act(() => result.current.onAutoTargetFps(57));
    await act(async () => vi.advanceTimersByTimeAsync(200));
    expect(mocks.setAutoTdpConfig).toHaveBeenLastCalledWith(57, 12, "game", "100", "100", null, 20);
    expect(result.current.tdp?.auto_config).toEqual(own);
    expect(mocks.setTdpFollowGlobal).not.toHaveBeenCalled();
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
