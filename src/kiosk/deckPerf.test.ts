import { describe, expect, it, vi } from "vitest";

vi.mock("@decky/api", () => ({ callable: () => vi.fn() }));
vi.mock("@decky/ui", () => ({ Router: {} }));
vi.mock("../components/AutoTdpNoticeModal", () => ({ openAutoTdpNoticeModal: vi.fn() }));

import type { TdpState } from "../api";
import { createDeckPerf, type DeckPerfDeps } from "./deckPerf";

const AUTO = { enabled: false, target_fps: 40, initial_tdp: 6, min_tdp: null, max_tdp: null };

function tdpState(patch: Partial<TdpState> = {}): TdpState {
  return {
    supported: true,
    tdp_control_enabled: true,
    supports_auto_tdp: true,
    unit: "level",
    follows_global: true,
    on_ac: false,
    limits: { min: 1, default: 6, max: 10, max_ac: 10 },
    auto_limits: { min: 1, default: 6, max: 10, max_ac: 10 },
    auto_request_limits: { min: 1, default: 6, max: 10, max_ac: 10 },
    watts: 6,
    global_watts: 6,
    levels: { pl1: 6, pl2: 6, pl3: 6 },
    global_levels: { pl1: 6, pl2: 6, pl3: 6 },
    boost_mode: "estable",
    global_boost_mode: "estable",
    presets: { quiet: 3, balanced: 6, turbo: 10, turbo_ac: 10 },
    auto_config: AUTO,
    global_auto_config: AUTO,
    auto_target_max_fps: 60,
    seen_autotdp_notice: true,
    ...patch,
  } as unknown as TdpState;
}

function deps(state: TdpState, patch: Partial<DeckPerfDeps> = {}) {
  const call = {
    applyPreset: vi.fn(async () => ({})),
    setWatts: vi.fn(async () => ({})),
    setAuto: vi.fn(async () => ({ auto_tdp: true })),
    setAutoConfig: vi.fn(async () => state),
    seenNotice: vi.fn(async () => true),
  };
  const d: DeckPerfDeps = {
    tdp: async () => state,
    presets: async () => null,
    power: async () => null,
    game: () => null,
    autoModuleOn: () => true,
    t: (key) => key,
    confirmAutoNotice: vi.fn(),
    call: call as unknown as DeckPerfDeps["call"],
    ...patch,
  };
  return { d, call };
}

describe("deck performance view", () => {
  it("resolves level, range and the builtin presets with the active one lit", async () => {
    const { d } = deps(tdpState());
    const view = await createDeckPerf(d)["perf.view"]();
    expect(view).toMatchObject({ ready: true, levels: true, value: 6, shown: 6, min: 1, max: 10, autoOn: false, target: null });
    expect(view.presets.map((p) => [p.id, p.active])).toEqual([["quiet", false], ["balanced", true], ["turbo", false]]);
    expect(view.presets[1].title).toBe("tdp.preset.balanced");
  });

  it("is not ready while another tool owns TDP", async () => {
    const { d } = deps(tdpState({ tdp_control_enabled: false }));
    const view = await createDeckPerf(d)["perf.view"]();
    expect(view.ready).toBe(false);
    expect(view.autoReady).toBe(false);
  });

  it("applies a preset to the game's own profile when the game does not follow global", async () => {
    const { d, call } = deps(tdpState({ follows_global: false }), { game: () => ({ appid: "894020" }) });
    await createDeckPerf(d)["perf.preset"](["turbo"]);
    expect(call.applyPreset).toHaveBeenCalledWith(10, "game", "894020", null, "894020");
  });

  it("clamps a level to the range and writes the global scope when the game follows it", async () => {
    const { d, call } = deps(tdpState(), { game: () => ({ appid: "894020" }) });
    await createDeckPerf(d)["perf.level"]([42]);
    expect(call.setWatts).toHaveBeenCalledWith(10, "global", null, "894020");
  });

  it("sets an fps target and turns automatic TDP on", async () => {
    const { d, call } = deps(tdpState());
    await createDeckPerf(d)["perf.target"]([45]);
    expect(call.setAutoConfig).toHaveBeenCalledWith(45, 6, "global", null, null, null, null);
    expect(call.setAuto).toHaveBeenCalledWith(true, "global", null, null);
  });

  it("asks for the one-time automatic TDP notice before the first enable", async () => {
    const { d, call } = deps(tdpState({ seen_autotdp_notice: false }));
    await createDeckPerf(d)["perf.target"]([45]);
    expect(call.setAuto).not.toHaveBeenCalled();
    const confirm = (d.confirmAutoNotice as ReturnType<typeof vi.fn>).mock.calls[0][0] as () => void;
    confirm();
    expect(call.seenNotice).toHaveBeenCalledWith(true);
    expect(call.setAuto).toHaveBeenCalledWith(true, "global", null, null);
  });

  it("a free target turns automatic TDP off and manual writes are refused while it runs", async () => {
    const on = { ...AUTO, enabled: true, target_fps: 45 };
    const { d, call } = deps(tdpState({ auto_config: on, global_auto_config: on }));
    const perf = createDeckPerf(d);
    expect((await perf["perf.view"]()).target).toBe(45);
    await perf["perf.target"]([null]);
    expect(call.setAuto).toHaveBeenCalledWith(false, "global", null, null);
    await expect(perf["perf.level"]([3])).rejects.toThrow("unsupported");
    await expect(perf["perf.preset"](["quiet"])).rejects.toThrow("unsupported");
  });

  it("keeps automatic TDP off the screen when its module is disabled", async () => {
    const { d } = deps(tdpState(), { autoModuleOn: () => false });
    const view = await createDeckPerf(d)["perf.view"]();
    expect(view.autoReady).toBe(false);
    await expect(createDeckPerf(d)["perf.target"]([45])).rejects.toThrow("unsupported");
  });
});
