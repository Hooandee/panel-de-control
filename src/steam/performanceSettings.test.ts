import { beforeEach, describe, expect, it, vi } from "vitest";
import { steamRefreshRateForFps, readPerformanceSettings, writePerformanceSetting, PerformanceSettingsDeps, PerfSettingsStore } from "./performanceSettings";

import { resetSteamPerformanceDiagnostics, steamPerformanceDiagnostics } from "./performanceDiagnostics";

beforeEach(resetSteamPerformanceDiagnostics);

function fixture() {
  const store: PerfSettingsStore = {
    nCurrentGameID: "42", nActiveProfileGameID: "42",
    msgSettingsPerApp: { fps_limit: 60, fps_limit_external: 120, fsr_sharpness: 5,
      display_refresh_manual_hz: 60, display_external_refresh_manual_hz: 120,
      is_vrr_enabled: false, split_scaling_filter: 3, split_scaling_scaler: 1 },
    msgSettingsGlobal: { allow_external_display_refresh_control: true },
    msgLimits: { disable_refresh_rate_management: true, fps_limit_options: [15, 30, 60, 0],
      fps_limit_options_external: [60, 120, 240, 0], fsr_sharpness_min: 0, fsr_sharpness_max: 5,
      is_manual_display_refresh_rate_available: true, display_refresh_manual_hz_min: 40, display_refresh_manual_hz_max: 60,
      display_external_refresh_manual_hz_min: 60, display_external_refresh_manual_hz_max: 240,
      is_vrr_supported: true, split_scaling_filters_available: [3, 2, 1], split_scaling_scalers_available: [1, 2, 3, 4, 5] },
    SetFPSLimit: vi.fn(), SetDisplayRefreshRateManualHz: vi.fn(), SetFSRSharpness: vi.fn(),
    SetSplitScalingFilter: vi.fn(), SetSplitScalingScaler: vi.fn(), SetVRREnabled: vi.fn(), ResetCurrentPerfProfileSettings: vi.fn(),
  };
  const settings: Record<string, unknown> = { gamescope_app_target_framerate: 60, gamescope_disable_framelimit: false,
    gamescope_enable_app_target_framerate: true, gamescope_allow_tearing: false, steamos_vrs_enabled: false };
  const set = vi.fn();
  const display = { external: false, isVrrCapable: true, supportedRefreshRates: [40, 60] };
  const gamescope = { is_app_refresh_rate_supported: true, is_refresh_rate_switching_restricted: false,
    active_display_info: { supported_frame_rates: [30, 40, 60] } };
  const steamOs = { is_vrs_available: true };
  const deps: PerformanceSettingsDeps = { store: () => store, runningGameId: () => 42,
    settings: { get: (name) => settings[name], set }, display: () => display,
    gamescope: () => gamescope, steamOs: () => steamOs };
  return { deps, store, settings, set, display, gamescope, steamOs };
}
const game = { scope: "game" as const, runningGameId: 42 };

describe("Steam settings adapter", () => {
  it("reads verified LCD controls without invoking setters or manufacturing legacy paths", () => {
    const { deps, store, set } = fixture();
    const controls = readPerformanceSettings(deps);
    expect(controls.map((control) => control.id)).toEqual([
      "splitScalingFilter", "scalingMode", "sharpness", "vrr",
      "allowTearing", "variableResolution", "disableFrameLimit", "appFrameRate", "reset",
    ]);
    expect(controls.find((control) => control.id === "scalingMode")).toMatchObject({ options: [
      { value: 1, label: "auto" }, { value: 2, label: "integer" }, { value: 3, label: "fit" },
      { value: 4, label: "fill" }, { value: 5, label: "stretch" },
    ] });
    expect(store.SetFPSLimit).not.toHaveBeenCalled();
    expect(set).not.toHaveBeenCalled();
  });

  it.each([false, true])("uses the exact external flag for FPS and Hz (external=%s)", async (external) => {
    const { deps, store, display } = fixture();
    store.msgLimits!.disable_refresh_rate_management = false;
    display.external = external;
    display.supportedRefreshRates = external ? [60, 120, 240] : [40, 60];
    expect(await writePerformanceSetting(deps, game, "legacyFrameRate", external ? 240 : 30)).toEqual({ status: "request_sent" });
    expect(store.SetFPSLimit).toHaveBeenCalledWith(external, external ? 240 : 30);
    await writePerformanceSetting(deps, game, "refreshRate", external ? 240 : 40);
    expect(store.SetDisplayRefreshRateManualHz).toHaveBeenCalledWith(external, external ? 240 : 40);
  });

  it.each([
    ["appFrameRate", 40, "gamescope_app_target_framerate"],
    ["disableFrameLimit", true, "gamescope_disable_framelimit"],
    ["variableResolution", true, "steamos_vrs_enabled"],
    ["allowTearing", true, "gamescope_allow_tearing"],
  ] as const)("writes only the requested %s setting", async (id, value, key) => {
    const { deps, set } = fixture();
    expect(await writePerformanceSetting(deps, game, id, value)).toEqual({ status: "request_sent" });
    expect(set).toHaveBeenCalledExactlyOnceWith(key, value);
  });

  it.each(["sharpness", "splitScalingFilter", "scalingMode", "legacyFrameRate", "appFrameRate"] as const)("rejects invalid %s values", async (id) => {
    const { deps, store, set } = fixture();
    if (id === "legacyFrameRate") store.msgLimits!.disable_refresh_rate_management = false;
    expect(await writePerformanceSetting(deps, game, id, 9999)).toEqual({ status: "invalid_value" });
    expect(set).not.toHaveBeenCalled();
    expect(store.SetFSRSharpness).not.toHaveBeenCalled();
  });

  it("validates integer steps and toggle types and skips unchanged values", async () => {
    const { deps } = fixture();
    expect(await writePerformanceSetting(deps, game, "sharpness", 1.5)).toEqual({ status: "invalid_value" });
    expect(await writePerformanceSetting(deps, game, "vrr", 1)).toEqual({ status: "invalid_value" });
    expect(await writePerformanceSetting(deps, game, "sharpness", 5)).toEqual({ status: "unchanged" });
  });

  it.each([
    ["43", "43", game], ["42", "769", game], ["769", "769", game],
    ["42", "42", { scope: "global" as const, runningGameId: 42 }],
    [undefined, "42", game], ["-42", "42", game],
  ])("rejects mismatched or unknown context %s/%s", async (current, active, context) => {
    const { deps, store } = fixture();
    store.nCurrentGameID = current; store.nActiveProfileGameID = active;
    expect(await writePerformanceSetting(deps, context, "sharpness", 4)).toEqual({ status: "context_mismatch" });
    expect(store.SetFSRSharpness).not.toHaveBeenCalled();
  });

  it("allows confirmed home global with a residual current game and rejects a changed live game", async () => {
    const { deps, store } = fixture();
    store.nCurrentGameID = "3764200"; store.nActiveProfileGameID = "769";
    deps.runningGameId = () => null;
    expect(await writePerformanceSetting(deps, { scope: "global", runningGameId: null }, "sharpness", 4)).toEqual({ status: "request_sent" });
    expect(await writePerformanceSetting(deps, game, "sharpness", 4)).toEqual({ status: "context_mismatch" });
  });

  it("validates non-Steam GameID64 before writing", async () => {
    const { deps, store } = fixture();
    const appid = 3570110851;
    const id = ((BigInt(appid) << BigInt(32)) | (BigInt(2) << BigInt(24))).toString();
    store.nCurrentGameID = store.nActiveProfileGameID = id;
    deps.runningGameId = () => appid;
    expect(await writePerformanceSetting(deps, { scope: "game", runningGameId: appid }, "sharpness", 4)).toEqual({ status: "request_sent" });
  });

  it("fails closed when live capabilities or bounds disappear", async () => {
    const { deps, store, display, steamOs, gamescope } = fixture();
    display.isVrrCapable = false; steamOs.is_vrs_available = false;
    gamescope.is_refresh_rate_switching_restricted = true;
    delete store.msgLimits!.fsr_sharpness_max;
    for (const id of ["vrr", "variableResolution", "appFrameRate", "sharpness"] as const) {
      expect(await writePerformanceSetting(deps, game, id, 4)).toEqual({ status: "unavailable" });
    }
  });

  it("preserves verified FPS choices and expands VRR only inside observed bounds", () => {
    const { deps, store, gamescope } = fixture();
    gamescope.active_display_info.supported_frame_rates = [40, 42];
    store.msgSettingsPerApp!.is_vrr_enabled = true;
    deps.settings!.get = (name) => name === "gamescope_app_target_framerate" ? 41
      : name === "gamescope_enable_app_target_framerate" ? true : false;
    expect(readPerformanceSettings(deps).find((control) => control.id === "appFrameRate")).toMatchObject({
      options: [{ value: 40 }, { value: 41 }, { value: 42 }],
    });
  });

  it("reports writes as requests, never applied, and contains thrown getters/setters", async () => {
    const { deps, store } = fixture();
    store.SetFSRSharpness = () => { throw new Error("failed"); };
    expect(await writePerformanceSetting(deps, game, "sharpness", 4)).toEqual({ status: "failed" });
    Object.defineProperty(store, "msgLimits", { get() { throw new Error("unavailable"); } });
    expect(readPerformanceSettings(deps).map(c => c.id)).toEqual(["allowTearing", "variableResolution", "reset"]);
  });
});

it("matches Steam refresh multiples without inventing unsupported rates", () => {
  expect(steamRefreshRateForFps(30, [40, 60])).toBe(60);
  expect(steamRefreshRateForFps(40, [40, 60])).toBe(40);
  expect(steamRefreshRateForFps(40, [40, 60, 80, 90])).toBe(80);
  expect(steamRefreshRateForFps(35, [40, 60])).toBeUndefined();
  expect(steamRefreshRateForFps(0, [60])).toBeUndefined();
  expect(steamRefreshRateForFps(60, [])).toBeUndefined();
});

it("shows paired Hz only when Steam supplies rates and VRR is disabled", () => {
  const { deps, store, gamescope } = fixture();
  deps.gamescope = () => ({ ...gamescope, active_display_info: {
    supported_frame_rates: [30, 40, 60], supported_refresh_rates: [40, 60],
  }});
  const read = () => readPerformanceSettings(deps).find(c => c.id === "appFrameRate");
  const paired = read();
  expect(paired?.kind === "options" && paired.options[0].refreshHz).toBe(60);
  store.msgSettingsPerApp!.is_vrr_enabled = true;
  const vrr = read();
  expect(vrr?.kind === "options" && vrr.options[0].refreshHz).toBeUndefined();
});


it("keeps independent controls readable and writable when a client setting throws", async () => {
  const { deps, store } = fixture();
  const get = deps.settings!.get;
  deps.settings!.get = name => {
    if (name === "gamescope_allow_tearing") throw new Error("query unavailable");
    return get(name);
  };
  const ids = readPerformanceSettings(deps).map(c => c.id);
  expect(ids).not.toContain("allowTearing");
  expect(ids).toContain("appFrameRate");
  expect(ids).toContain("splitScalingFilter");
  expect(await writePerformanceSetting(deps, game, "splitScalingFilter", 1)).toEqual({ status: "request_sent" });
  expect(store.SetSplitScalingFilter).toHaveBeenCalledWith(1);
  expect(steamPerformanceDiagnostics()?.current["read_allowTearing"]).toMatchObject({ status: "read_failed", control_id: "allowTearing" });
});

it("contains individual store getters and display service failures", () => {
  const { deps, store } = fixture();
  Object.defineProperty(store.msgSettingsPerApp, "split_scaling_filter", { get() { throw new Error("filter unavailable"); } });
  deps.display = () => { throw new Error("display unavailable"); };
  const ids = readPerformanceSettings(deps).map(c => c.id);
  expect(ids).toContain("scalingMode");
  expect(ids).toContain("allowTearing");
  expect(ids).toContain("disableFrameLimit");
  expect(ids).toContain("reset");
  expect(ids).not.toContain("splitScalingFilter");
  expect(ids).not.toContain("sharpness");
});

it("recovers a failed control when its provider recovers", () => {
  const { deps } = fixture();
  const get = deps.settings!.get;
  deps.settings!.get = () => { throw new Error("unavailable"); };
  readPerformanceSettings(deps);
  deps.settings!.get = get;
  expect(readPerformanceSettings(deps).map(c => c.id)).toContain("allowTearing");
  expect(steamPerformanceDiagnostics()?.current["read_allowTearing"]).toMatchObject({ status: "available" });
});

function legacyFixture(filter = 4) {
  const f = fixture();
  Object.assign(f.store.msgLimits!, { is_split_scaling_and_filtering_supported: false, is_nis_supported: true, nis_sharpness_min: 0, nis_sharpness_max: 8 });
  Object.assign(f.store.msgSettingsPerApp!, { scaling_filter: filter, nis_sharpness: 4 });
  f.store.SetScalingFilter = vi.fn();
  f.store.SetNISSharpness = vi.fn();
  return f;
}

it("preserves the historical combined filter contract without offering split controls", async () => {
  const { deps, store } = legacyFixture();
  const controls = readPerformanceSettings(deps);
  expect(controls.find(c => c.id === "combinedScaling")).toMatchObject({ kind: "options", value: 4, options: [
    { value: 4, label: "linear" }, { value: 2, label: "nearest" }, { value: 3, label: "integer" },
    { value: 1, label: "fsr" }, { value: 5, label: "nis" },
  ] });
  expect(controls.map(c => c.id)).not.toContain("splitScalingFilter");
  expect(controls.map(c => c.id)).not.toContain("scalingMode");
  expect(controls.map(c => c.id)).not.toContain("sharpness");
  expect(await writePerformanceSetting(deps, game, "combinedScaling", 1)).toEqual({ status: "request_sent" });
  expect(store.SetScalingFilter).toHaveBeenCalledExactlyOnceWith(1);
});

it.each([[1, "fsrSharpness", "SetFSRSharpness"], [5, "nisSharpness", "SetNISSharpness"]] as const)(
  "preserves the legacy filter %s sharpness contract", async (filter, id, setter) => {
    const { deps, store } = legacyFixture(filter);
    expect(readPerformanceSettings(deps).find(c => c.id === id)).toMatchObject({ kind: "slider", min: 0, max: filter === 1 ? 5 : 8 });
    expect(await writePerformanceSetting(deps, game, id, 3)).toEqual({ status: "request_sent" });
    expect(store[setter]).toHaveBeenCalledExactlyOnceWith(3);
  },
);

it("requires observed NIS support and sharpness bounds", async () => {
  const { deps, store } = legacyFixture(1);
  store.msgLimits!.is_nis_supported = false;
  expect(await writePerformanceSetting(deps, game, "combinedScaling", 5)).toEqual({ status: "invalid_value" });
  delete store.msgLimits!.fsr_sharpness_max;
  expect(readPerformanceSettings(deps).map(c => c.id)).not.toContain("fsrSharpness");
  expect(store.SetScalingFilter).not.toHaveBeenCalled();
});

it("recognizes pre-split clients only with the observed legacy setting and setter", () => {
  const { deps, store } = legacyFixture();
  delete store.msgLimits!.is_split_scaling_and_filtering_supported;
  delete store.SetSplitScalingFilter;
  delete store.SetSplitScalingScaler;
  expect(readPerformanceSettings(deps).map(c => c.id)).toContain("combinedScaling");
  delete store.SetScalingFilter;
  expect(readPerformanceSettings(deps).map(c => c.id)).not.toContain("combinedScaling");
});

it("supports historical split NIS when advertised and does not duplicate legacy controls", async () => {
  const { deps, store } = legacyFixture(5);
  store.msgLimits!.is_split_scaling_and_filtering_supported = true;
  store.msgLimits!.split_scaling_filters_available = [1, 2, 3, 4];
  store.msgSettingsPerApp!.split_scaling_filter = 4;
  const controls = readPerformanceSettings(deps);
  expect(controls.map(c => c.id)).not.toContain("combinedScaling");
  expect(controls.map(c => c.id)).toContain("nisSharpness");
  expect(await writePerformanceSetting(deps, game, "splitScalingFilter", 1)).toEqual({ status: "request_sent" });
});
