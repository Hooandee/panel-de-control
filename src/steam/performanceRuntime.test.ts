// @vitest-environment happy-dom
import { beforeEach, describe, expect, it, vi } from "vitest";

const decky = vi.hoisted(() => ({
  findModuleByExport: vi.fn(),
  findModuleExport: vi.fn(),
}));

vi.mock("@decky/ui", () => decky);

import {
  discoverSteamPerformanceComponents,
  resetSteamPerformanceRuntimeCache,
  resolveSteamPerformanceStore,
  syncSteamPerformanceProfile,
  subscribeSteamPerformanceState,
} from "./performanceRuntime";
import { steamPerformanceDiagnostics } from "./performanceDiagnostics";

const component = (...tokens: string[]) => {
  const candidate = () => null;
  Object.defineProperty(candidate, "toString", { value: () => tokens.join(" ") });
  return candidate;
};

const diagnostic = (area: string) => steamPerformanceDiagnostics()?.current[area];
const diagnosticEvents = (area: string) => (
  steamPerformanceDiagnostics()?.events.filter((event) => event.area === area) ?? []
);

describe("Steam performance runtime", () => {
  beforeEach(() => {
    resetSteamPerformanceRuntimeCache();
    decky.findModuleByExport.mockReset();
    decky.findModuleExport.mockReset();
    delete (window as Window & { SystemPerfStore?: unknown }).SystemPerfStore;
    delete (window as Window & { webpackChunksteamui?: unknown }).webpackChunksteamui;
  });

  it("discovers controls only inside the module carrying Steam's reset export", () => {
    const reset = component(
      "#QuickAccess_Tab_Perf_ResetToDefault",
      "ResetCurrentPerfProfileSettings",
    );
    const tearing = component(
      "#QuickAccess_Tab_Perf_EnableTearing",
      "gamescope_allow_tearing",
    );
    const module = { reset, tearing };
    decky.findModuleByExport.mockImplementation((predicate: (value: unknown) => boolean) => {
      expect(predicate(reset)).toBe(true);
      expect(predicate(tearing)).toBe(false);
      return module;
    });

    const controls = discoverSteamPerformanceComponents();
    const cached = discoverSteamPerformanceComponents();

    expect(controls.reset).toBe(reset);
    expect(controls.allowTearing).toBe(tearing);
    expect(cached).toBe(controls);
    expect(decky.findModuleByExport).toHaveBeenCalledOnce();
  });

  it("discovers a performance module loaded after Decky's startup snapshot", () => {
    const reset = component(
      "#QuickAccess_Tab_Perf_ResetToDefault",
      "ResetCurrentPerfProfileSettings",
    );
    const vrr = component(
      "#QuickAccess_Tab_Perf_EnableVRR",
      "#QuickAccess_Tab_Perf_VRR_NotCapable",
    );
    const module = { reset, vrr };
    const runtime = Object.assign(
      (_id: string) => module,
      {
        m: {
          "83571": function performanceFactory() {
            return "#QuickAccess_Tab_Perf_ResetToDefault ResetCurrentPerfProfileSettings";
          },
        },
      },
    );
    (window as Window & { webpackChunksteamui?: unknown }).webpackChunksteamui = {
      push: (_chunk: [unknown[], Record<string, never>, (value: typeof runtime) => void]) => {
        _chunk[2](runtime);
      },
    };
    decky.findModuleByExport.mockReturnValue(undefined);

    const controls = discoverSteamPerformanceComponents();

    expect(controls.reset).toBe(reset);
    expect(controls.vrr).toBe(vrr);
  });

  it("prefers controls from the current CEF generation over Decky's old snapshot", () => {
    const staleReset = component(
      "#QuickAccess_Tab_Perf_ResetToDefault",
      "ResetCurrentPerfProfileSettings",
    );
    const staleVrr = component(
      "#QuickAccess_Tab_Perf_EnableVRR",
      "#QuickAccess_Tab_Perf_VRR_NotCapable",
    );
    decky.findModuleByExport.mockReturnValue({ reset: staleReset, vrr: staleVrr });

    const currentReset = component(
      "#QuickAccess_Tab_Perf_ResetToDefault",
      "ResetCurrentPerfProfileSettings",
    );
    const currentVrr = component(
      "#QuickAccess_Tab_Perf_EnableVRR",
      "#QuickAccess_Tab_Perf_VRR_NotCapable",
    );
    const runtime = Object.assign(
      (_id: string) => ({ reset: currentReset, vrr: currentVrr }),
      {
        m: {
          "83571": function currentPerformanceFactory() {
            return "#QuickAccess_Tab_Perf_ResetToDefault ResetCurrentPerfProfileSettings";
          },
        },
      },
    );
    (window as Window & { webpackChunksteamui?: unknown }).webpackChunksteamui = {
      push: (_chunk: [unknown[], Record<string, never>, (value: typeof runtime) => void]) => {
        _chunk[2](runtime);
      },
    };

    const controls = discoverSteamPerformanceComponents();

    expect(controls.reset).toBe(currentReset);
    expect(controls.vrr).toBe(currentVrr);
    expect(decky.findModuleByExport).not.toHaveBeenCalled();
  });

  it("does not reuse Decky's old controls while the current module is still loading", () => {
    const staleReset = component(
      "#QuickAccess_Tab_Perf_ResetToDefault",
      "ResetCurrentPerfProfileSettings",
    );
    const staleVrr = component(
      "#QuickAccess_Tab_Perf_EnableVRR",
      "#QuickAccess_Tab_Perf_VRR_NotCapable",
    );
    decky.findModuleByExport.mockReturnValue({ reset: staleReset, vrr: staleVrr });
    const runtime = Object.assign(
      (_id: string) => ({}),
      { m: { "100": function unrelatedFactory() { return "other"; } } },
    );
    (window as Window & { webpackChunksteamui?: unknown }).webpackChunksteamui = {
      push: (_chunk: [unknown[], Record<string, never>, (value: typeof runtime) => void]) => {
        _chunk[2](runtime);
      },
    };

    expect(discoverSteamPerformanceComponents()).toEqual({});
  });

  it("reports a rejected capture of Steam's current webpack runtime", () => {
    (window as Window & { webpackChunksteamui?: unknown }).webpackChunksteamui = {
      push() {
        throw new Error("chunk capture rejected");
      },
    };
    decky.findModuleByExport.mockReturnValue(undefined);

    expect(discoverSteamPerformanceComponents()).toEqual({});
    expect(diagnostic("runtime")).toEqual({
      status: "capture_failed",
      error: {
        name: "Error",
        message: "chunk capture rejected",
      },
    });
  });

  it("rejects two viable performance modules in the live runtime", () => {
    const first = {
      reset: component("#QuickAccess_Tab_Perf_ResetToDefault", "ResetCurrentPerfProfileSettings"),
      vrr: component("#QuickAccess_Tab_Perf_EnableVRR", "#QuickAccess_Tab_Perf_VRR_NotCapable"),
    };
    const second = {
      reset: component("#QuickAccess_Tab_Perf_ResetToDefault", "ResetCurrentPerfProfileSettings"),
      tearing: component("#QuickAccess_Tab_Perf_EnableTearing", "gamescope_allow_tearing"),
    };
    const runtime = Object.assign(
      (id: string) => id === "1" ? first : second,
      {
        m: {
          "1": function firstFactory() {
            return "#QuickAccess_Tab_Perf_ResetToDefault ResetCurrentPerfProfileSettings";
          },
          "2": function secondFactory() {
            return "#QuickAccess_Tab_Perf_ResetToDefault ResetCurrentPerfProfileSettings";
          },
        },
      },
    );
    (window as Window & { webpackChunksteamui?: unknown }).webpackChunksteamui = {
      push: (_chunk: [unknown[], Record<string, never>, (value: typeof runtime) => void]) => {
        _chunk[2](runtime);
      },
    };

    expect(discoverSteamPerformanceComponents()).toEqual({});
    expect(diagnostic("components")).toEqual({
      status: "ambiguous",
      source: "current_runtime",
      candidate_count: 2,
    });
  });

  it("prefers Steam's live global store over a stale webpack export", () => {
    const live = {
      msgLimits: {
        disable_refresh_rate_management: true,
        is_split_scaling_and_filtering_supported: false,
      },
      nCurrentGameID: "42",
      nActiveProfileGameID: "769",
      SetGameSpecificProfileEnabled() {},
    };
    (window as Window & { SystemPerfStore?: unknown }).SystemPerfStore = live;

    expect(resolveSteamPerformanceStore()).toBe(live);
    expect(decky.findModuleExport).not.toHaveBeenCalled();
    expect(diagnostic("store")).toEqual({
      status: "ready",
      source: "global",
    });
  });

  it("does not let diagnostic getters invalidate a resolved store", () => {
    const live = {
      msgLimits: {},
      get nCurrentGameID(): string {
        throw new Error("profile id unavailable");
      },
      get nActiveProfileGameID(): string {
        throw new Error("active profile unavailable");
      },
    };
    (window as Window & { SystemPerfStore?: unknown }).SystemPerfStore = live;

    expect(resolveSteamPerformanceStore()).toBe(live);
    expect(diagnostic("store")).toEqual({ status: "ready", source: "global" });
  });

  it("selects the running game's Steam profile for game scope", () => {
    const state = { active: "769" };
    (window as Window & { SystemPerfStore?: unknown }).SystemPerfStore = {
      msgLimits: {},
      nCurrentGameID: "42",
      get nActiveProfileGameID() { return state.active; },
      SetGameSpecificProfileEnabled(enabled: boolean) {
        state.active = enabled ? "42" : "769";
      },
    };

    syncSteamPerformanceProfile("game", 42);

    expect(state.active).toBe("42");
  });

  it("records a profile request and its later readback convergence", () => {
    const state = { active: "769" };
    (window as Window & { SystemPerfStore?: unknown }).SystemPerfStore = {
      msgLimits: {},
      nCurrentGameID: "42",
      get nActiveProfileGameID() { return state.active; },
      SetGameSpecificProfileEnabled(enabled: boolean) {
        state.active = enabled ? "42" : "769";
      },
    };

    syncSteamPerformanceProfile("game", 42);
    syncSteamPerformanceProfile("game", 42);

    expect(diagnostic("profile")).toEqual({
      status: "already_synced",
      scope: "game",
      running_game_id: "42",
      current_game_id: "42",
      active_profile_game_id: "42",
    });
    expect(diagnosticEvents("profile")).toEqual(expect.arrayContaining([
      expect.objectContaining({
        data: expect.objectContaining({
          status: "request_sent",
        }),
      }),
      expect.objectContaining({
        data: expect.objectContaining({ status: "already_synced" }),
      }),
    ]));
  });

  it("does not turn a successful profile write into a diagnostic failure", () => {
    let written = false;
    const store = {
      msgLimits: {},
      get nCurrentGameID(): string {
        if (written) throw new Error("post-write readback unavailable");
        return "42";
      },
      get nActiveProfileGameID(): string {
        if (written) throw new Error("post-write readback unavailable");
        return "769";
      },
      SetGameSpecificProfileEnabled() {
        written = true;
      },
    };
    (window as Window & { SystemPerfStore?: unknown }).SystemPerfStore = store;

    syncSteamPerformanceProfile("game", 42);

    expect(written).toBe(true);
    expect(diagnostic("profile")).toMatchObject({ status: "request_sent" });
  });

  it("returns Steam to its global profile for global scope", () => {
    const state = { active: "42" };
    (window as Window & { SystemPerfStore?: unknown }).SystemPerfStore = {
      msgLimits: {},
      nCurrentGameID: "42",
      get nActiveProfileGameID() { return state.active; },
      SetGameSpecificProfileEnabled(enabled: boolean) {
        state.active = enabled ? "42" : "769";
      },
    };

    syncSteamPerformanceProfile("global", 42);

    expect(state.active).toBe("769");
  });

  it("records a sanitized profile sync failure", () => {
    (window as Window & { SystemPerfStore?: unknown }).SystemPerfStore = {
      msgLimits: {},
      nCurrentGameID: "42",
      nActiveProfileGameID: "769",
      SetGameSpecificProfileEnabled() {
        throw new Error("Steam profile setter changed\ninside private runtime");
      },
    };

    syncSteamPerformanceProfile("game", 42);

    expect(diagnostic("profile")).toEqual({
      status: "request_failed",
      scope: "game",
      running_game_id: "42",
      current_game_id: "42",
      active_profile_game_id: "769",
      error: {
        name: "Error",
        message: "Steam profile setter changed inside private runtime",
      },
    });
  });

  it("reports missing game-profile support on older Steam clients", () => {
    (window as Window & { SystemPerfStore?: unknown }).SystemPerfStore = {
      msgLimits: {},
      nCurrentGameID: "42",
      nActiveProfileGameID: "769",
    };

    syncSteamPerformanceProfile("game", 42);

    expect(diagnostic("profile")).toEqual({
      status: "setter_unavailable",
      scope: "game",
      running_game_id: "42",
    });
  });

  it("selects the game profile when Steam is still on its global sentinel", () => {
    const state = { current: "769", active: "769" };
    (window as Window & { SystemPerfStore?: unknown }).SystemPerfStore = {
      msgLimits: {},
      get nCurrentGameID() { return state.current; },
      get nActiveProfileGameID() { return state.active; },
      SetGameSpecificProfileEnabled(enabled: boolean) {
        state.current = enabled ? "42" : "769";
        state.active = state.current;
      },
    };

    syncSteamPerformanceProfile("game", 42);

    expect(state).toEqual({ current: "42", active: "42" });
  });

  it("matches a non-Steam shortcut GameID64 to its running appid", () => {
    const shortcutAppId = 3570110851;
    const shortcutGameId = "15333509348173283328";
    const state = { active: "769" };
    (window as Window & { SystemPerfStore?: unknown }).SystemPerfStore = {
      msgLimits: {},
      nCurrentGameID: shortcutGameId,
      get nActiveProfileGameID() { return state.active; },
      SetGameSpecificProfileEnabled(enabled: boolean) {
        state.active = enabled ? shortcutGameId : "769";
      },
    };

    syncSteamPerformanceProfile("game", shortcutAppId);

    expect(state.active).toBe(shortcutGameId);
  });

  it("fails closed on GameID64 matching when an old client lacks BigInt", () => {
    const nativeBigInt = globalThis.BigInt;
    const setProfile = vi.fn();
    (window as Window & { SystemPerfStore?: unknown }).SystemPerfStore = {
      msgLimits: {},
      nCurrentGameID: "15333509348173283328",
      nActiveProfileGameID: "769",
      SetGameSpecificProfileEnabled: setProfile,
    };

    vi.stubGlobal("BigInt", undefined);
    try {
      syncSteamPerformanceProfile("game", 3570110851);
    } finally {
      vi.stubGlobal("BigInt", nativeBigInt);
    }

    expect(setProfile).not.toHaveBeenCalled();
  });

  it("does not change Steam when its foreground game differs from Panel de Control", () => {
    let active = "41";
    (window as Window & { SystemPerfStore?: unknown }).SystemPerfStore = {
      msgLimits: {},
      nCurrentGameID: "41",
      nActiveProfileGameID: active,
      SetGameSpecificProfileEnabled(enabled: boolean) {
        active = enabled ? "41" : "769";
      },
    };

    syncSteamPerformanceProfile("game", 42);

    expect(active).toBe("41");
  });

  it("reapplies a legacy game profile when a new surface lifecycle starts", () => {
    const setProfile = vi.fn();
    (window as Window & { SystemPerfStore?: unknown }).SystemPerfStore = {
      msgLimits: {},
      SetGameSpecificProfileEnabled: setProfile,
    };

    syncSteamPerformanceProfile("game", 42);
    syncSteamPerformanceProfile("game", 42);
    syncSteamPerformanceProfile("game", 42, true);

    expect(setProfile.mock.calls).toEqual([[true], [true]]);
  });

  it("hydrates the store singleton when Steam has not published the global yet", () => {
    const hydrated = { msgLimits: { disable_refresh_rate_management: true } };
    class SteamPerfStore {
      static Get() { return hydrated; }
      SetVRREnabled() {}
      SetSplitScalingScaler() {}
      ResetCurrentPerfProfileSettings() {}
    }
    decky.findModuleExport.mockImplementation((predicate: (value: unknown) => boolean) => {
      expect(predicate(SteamPerfStore)).toBe(true);
      return SteamPerfStore;
    });

    expect(resolveSteamPerformanceStore()).toBe(hydrated);
    expect(diagnostic("store")).toMatchObject({
      status: "ready",
      source: "legacy_snapshot",
    });
  });

  it("hydrates the current Steam runtime when Decky's store snapshot is stale", () => {
    const hydrated = { msgLimits: { is_split_scaling_and_filtering_supported: true } };
    class SteamPerfStore {
      static Get() { return hydrated; }
      SetVRREnabled() {}
      SetSplitScalingScaler() {}
      ResetCurrentPerfProfileSettings() {}
    }
    const runtime = Object.assign(
      vi.fn((_id: string) => ({ SteamPerfStore })),
      {
        m: {
          "66186": function storeFactory() {
            return "SetVRREnabled SetSplitScalingScaler ResetCurrentPerfProfileSettings";
          },
        },
      },
    );
    (window as Window & { webpackChunksteamui?: unknown }).webpackChunksteamui = {
      push: (_chunk: [unknown[], Record<string, never>, (value: typeof runtime) => void]) => {
        _chunk[2](runtime);
      },
    };
    decky.findModuleExport.mockReturnValue(undefined);

    expect(resolveSteamPerformanceStore()).toBe(hydrated);
    expect(resolveSteamPerformanceStore()).toBe(hydrated);
    expect(runtime).toHaveBeenCalledOnce();
    expect(diagnostic("store")).toMatchObject({
      status: "ready",
      source: "current_runtime",
    });
  });

  it.each([
    {
      missing: "VRR",
      Store: class SteamPerfStore {
        static Get() { return { msgLimits: { legacy: "without-vrr" } }; }
        SetSplitScalingScaler() {}
        ResetCurrentPerfProfileSettings() {}
      },
      factory: function legacyStoreWithoutVrrFactory(): string {
        return "SetSplitScalingScaler ResetCurrentPerfProfileSettings";
      },
      expected: "without-vrr",
    },
    {
      missing: "split scaling",
      Store: class SteamPerfStore {
        static Get() { return { msgLimits: { legacy: "without-split-scaling" } }; }
        SetVRREnabled() {}
        ResetCurrentPerfProfileSettings() {}
      },
      factory: function legacyStoreWithoutSplitScalingFactory(): string {
        return "SetVRREnabled ResetCurrentPerfProfileSettings";
      },
      expected: "without-split-scaling",
    },
  ])("discovers an older runtime without optional $missing support", ({ Store, factory, expected }) => {
    const runtime = Object.assign(
      vi.fn((_id: string) => ({ SteamPerfStore: Store })),
      {
        m: {
          legacy: factory,
        },
      },
    );
    (window as Window & { webpackChunksteamui?: unknown }).webpackChunksteamui = {
      push: (_chunk: [unknown[], Record<string, never>, (value: typeof runtime) => void]) => {
        _chunk[2](runtime);
      },
    };
    decky.findModuleExport.mockReturnValue(undefined);

    expect(resolveSteamPerformanceStore()?.msgLimits).toEqual({ legacy: expected });
  });

  it("rejects two distinct performance stores in the live runtime", () => {
    const stores = [{ msgLimits: {} }, { msgLimits: {} }];
    const storeClass = (index: number) => class SteamPerfStore {
      static Get() { return stores[index]; }
      SetVRREnabled() {}
      SetSplitScalingScaler() {}
      ResetCurrentPerfProfileSettings() {}
    };
    const modules = {
      "1": { SteamPerfStore: storeClass(0) },
      "2": { SteamPerfStore: storeClass(1) },
    };
    const runtime = Object.assign(
      (id: keyof typeof modules) => modules[id],
      {
        m: {
          "1": function firstStoreFactory() {
            return "SetVRREnabled SetSplitScalingScaler ResetCurrentPerfProfileSettings";
          },
          "2": function secondStoreFactory() {
            return "SetVRREnabled SetSplitScalingScaler ResetCurrentPerfProfileSettings";
          },
        },
      },
    );
    (window as Window & { webpackChunksteamui?: unknown }).webpackChunksteamui = {
      push: (_chunk: [unknown[], Record<string, never>, (value: typeof runtime) => void]) => {
        _chunk[2](runtime);
      },
    };
    class SnapshotStore {
      static Get() { return { msgLimits: {} }; }
      SetVRREnabled() {}
      SetSplitScalingScaler() {}
      ResetCurrentPerfProfileSettings() {}
    }
    decky.findModuleExport.mockReturnValue(SnapshotStore);

    expect(resolveSteamPerformanceStore()).toBeNull();
    expect(diagnostic("store")).toEqual({
      status: "ambiguous",
      source: "current_runtime",
      candidate_count: 2,
    });
  });

  it("defers state refresh until Steam's store callback has applied the payload", async () => {
    const unregister = vi.fn();
    let registered: (() => void) | undefined;
    const onChange = vi.fn();
    const steamClient = {
      System: {
        Perf: {
          RegisterForStateChanges(callback: () => void) {
            registered = callback;
            return { unregister };
          },
        },
      },
    };

    const cleanup = subscribeSteamPerformanceState(onChange, steamClient);
    registered?.();
    expect(onChange).not.toHaveBeenCalled();
    await Promise.resolve();
    expect(onChange).toHaveBeenCalledOnce();

    cleanup();
    expect(unregister).toHaveBeenCalledOnce();
  });

  it("records the lifecycle of Steam's performance subscription", () => {
    const unregister = vi.fn();
    const cleanup = subscribeSteamPerformanceState(vi.fn(), {
      System: {
        Perf: {
          RegisterForStateChanges: () => ({ unregister }),
        },
      },
    });

    expect(diagnostic("subscription")).toEqual({
      status: "registered",
      cleanup_available: true,
    });

    cleanup();

    expect(diagnostic("subscription")).toEqual({ status: "unregistered" });
  });

  it("preserves Steam's performance subscription receiver", () => {
    let receiver: unknown;
    const perf = {
      RegisterForStateChanges(this: unknown) {
        receiver = this;
      },
    };

    subscribeSteamPerformanceState(vi.fn(), { System: { Perf: perf } });

    expect(receiver).toBe(perf);
    expect(diagnostic("subscription")).toEqual({
      status: "registered",
      cleanup_available: false,
    });
  });

  it("reports a rejected Steam performance subscription", () => {
    subscribeSteamPerformanceState(vi.fn(), {
      System: {
        Perf: {
          RegisterForStateChanges() {
            throw new TypeError("subscription contract changed");
          },
        },
      },
    });

    expect(diagnostic("subscription")).toEqual({
      status: "registration_failed",
      error: {
        name: "TypeError",
        message: "subscription contract changed",
      },
    });
  });

  it("reports a rejected Steam performance unsubscription", () => {
    const cleanup = subscribeSteamPerformanceState(vi.fn(), {
      System: {
        Perf: {
          RegisterForStateChanges: () => ({
            unregister() {
              throw new Error("old CEF registration");
            },
          }),
        },
      },
    });

    cleanup();

    expect(diagnostic("subscription")).toEqual({
      status: "unregistration_failed",
      error: {
        name: "Error",
        message: "old CEF registration",
      },
    });
  });

  it("fails closed when Steam exposes neither store nor subscription", () => {
    decky.findModuleExport.mockReturnValue(undefined);

    expect(resolveSteamPerformanceStore()).toBeNull();
    expect(diagnostic("store")).toEqual({
      status: "unavailable",
      source: "none",
    });
    expect(subscribeSteamPerformanceState(vi.fn(), {})).toEqual(expect.any(Function));
    expect(() => subscribeSteamPerformanceState(vi.fn())).not.toThrow();
    expect(diagnostic("subscription")).toEqual({ status: "unavailable" });
  });

  it("reports why profile synchronization could not start", () => {
    decky.findModuleExport.mockReturnValue(undefined);

    syncSteamPerformanceProfile("game", 42);

    expect(diagnostic("profile")).toEqual({
      status: "store_unavailable",
      scope: "game",
      running_game_id: "42",
    });
  });
});
