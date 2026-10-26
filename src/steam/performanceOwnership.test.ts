import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({ owner: vi.fn(), game: vi.fn(), profile: vi.fn(), controls: vi.fn(), write: vi.fn(), enable: vi.fn(), diagnostic: vi.fn(), capabilities: vi.fn() }));
vi.mock("../api", () => ({ getGamePowerOwner: mocks.owner }));
vi.mock("../tdp/runningGame", () => ({ readRunningGame: mocks.game }));
vi.mock("./performanceSettingsRuntime", () => ({ createPerformanceSettingsDeps: () => ({ steamOs: mocks.capabilities }) }));
vi.mock("./performanceSettings", () => ({ readPerformanceSettings: mocks.controls, writePerformanceSetting: mocks.write }));
vi.mock("./performanceRuntime", () => ({ readSteamPerformanceProfile: mocks.profile, resolveSteamPerformanceStore: () => ({ SetGameSpecificProfileEnabled: mocks.enable }) }));
vi.mock("./performanceDiagnostics", () => ({ recordSteamPerformanceDiagnostic: mocks.diagnostic }));
import { startSteamPerformanceOwnership, runSteamPerformanceTransaction, reapplySteamPowerSettings, reapplyResetPowerSettings } from "./performanceOwnership";
const game = { appid: "42", liveAppid: 42, name: "Game" };
const owned = { supported: true, context_appid: "42", explicit_owner: "pdc", steam_settings: { sharpness: 4, vrr: true } };
async function flush() { for (let i = 0; i < 15; i++) await Promise.resolve(); }
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>((done) => { resolve = done; }); return { promise, resolve }; }
let stop: (() => void) | undefined;
beforeEach(() => {
  vi.useFakeTimers(); vi.clearAllMocks();
  mocks.capabilities.mockReturnValue({ is_tdp_limit_available: true, is_manual_gpu_clock_available: true });
  mocks.game.mockReturnValue(game); mocks.owner.mockResolvedValue(owned); mocks.profile.mockReturnValue("game");
  mocks.controls.mockReturnValue([{ id: "sharpness", kind: "slider", value: 5 }, { id: "vrr", kind: "toggle", value: false }, { id: "reset", kind: "action" }]);
  mocks.write.mockResolvedValue({ status: "request_sent" });
});
afterEach(async () => { stop?.(); stop = undefined; await flush(); vi.useRealTimers(); vi.unstubAllGlobals(); });

describe("persistent Steam performance ownership", () => {
  it.each(["steam", null])("does not write without explicit PDC ownership (%s)", async (owner) => {
    mocks.owner.mockResolvedValue({ ...owned, explicit_owner: owner });
    stop = startSteamPerformanceOwnership(); await flush();
    expect(mocks.write).not.toHaveBeenCalled(); expect(mocks.enable).not.toHaveBeenCalled();
  });
  it.each(["global", "game"])("does not reconcile persisted PDC ownership without backend support (%s)", async (profile) => {
    mocks.owner.mockResolvedValue({ ...owned, supported: false });
    mocks.profile.mockReturnValue(profile);
    stop = startSteamPerformanceOwnership();
    await flush();
    await vi.advanceTimersByTimeAsync(2000);
    expect(mocks.enable).not.toHaveBeenCalled();
    expect(mocks.write).not.toHaveBeenCalled();
  });
  it("reapplies only differing stored values and never reset", async () => {
    mocks.controls.mockReturnValue([{ id: "sharpness", kind: "slider", value: 5 }, { id: "vrr", kind: "toggle", value: true }, { id: "reset", kind: "action" }]);
    stop = startSteamPerformanceOwnership(); await flush();
    expect(mocks.write).toHaveBeenCalledExactlyOnceWith({ steamOs: mocks.capabilities }, { scope: "game", runningGameId: 42 }, "sharpness", 4);
    expect(mocks.diagnostic).toHaveBeenCalledWith("control", { status: "reconcile_request_sent", control_id: "sharpness" });
  });
  it("requests game profile only and waits for readback before settings", async () => {
    mocks.profile.mockReturnValue("global");
    stop = startSteamPerformanceOwnership(); await flush();
    expect(mocks.enable).toHaveBeenCalledExactlyOnceWith(true); expect(mocks.write).not.toHaveBeenCalled();
    mocks.profile.mockReturnValue("game");
    await vi.advanceTimersByTimeAsync(2000);
    expect(mocks.write).toHaveBeenCalledTimes(2);
  });
  it("does not write while profile is unknown", async () => {
    mocks.profile.mockReturnValue("unknown"); stop = startSteamPerformanceOwnership(); await flush();
    expect(mocks.write).not.toHaveBeenCalled(); expect(mocks.enable).not.toHaveBeenCalled();
  });
  it.each(["context", "unload"])("discards an ownership response after %s changes", async (change) => {
    const pending = deferred<typeof owned>(); mocks.owner.mockReturnValue(pending.promise);
    stop = startSteamPerformanceOwnership(); await flush();
    if (change === "unload") stop(); else mocks.game.mockReturnValue({ appid: "43", liveAppid: 43 });
    pending.resolve(owned); await flush();
    expect(mocks.write).not.toHaveBeenCalled(); expect(mocks.enable).not.toHaveBeenCalled();
  });
  it.each(["context", "unload"])("stops subsequent writes after %s during a write", async (change) => {
    const pending = deferred<{ status: string }>(); mocks.write.mockReturnValueOnce(pending.promise);
    stop = startSteamPerformanceOwnership(); await flush();
    expect(mocks.write).toHaveBeenCalledTimes(1);
    if (change === "unload") stop(); else mocks.game.mockReturnValue({ appid: "43", liveAppid: 43 });
    pending.resolve({ status: "request_sent" }); await flush();
    expect(mocks.write).toHaveBeenCalledTimes(1);
  });
  it("serializes with card work and skips queued lifecycle work after unload", async () => {
    const pending = deferred<void>();
    const card = runSteamPerformanceTransaction(() => pending.promise);
    stop = startSteamPerformanceOwnership(); await flush(); stop();
    expect(mocks.owner).not.toHaveBeenCalled();
    pending.resolve(); await card; await flush();
    expect(mocks.owner).not.toHaveBeenCalled(); expect(mocks.write).not.toHaveBeenCalled();
  });
  it("does not overlap polls while ownership lookup is pending", async () => {
    const pending = deferred<typeof owned>(); mocks.owner.mockReturnValue(pending.promise);
    stop = startSteamPerformanceOwnership(); await flush(); await vi.advanceTimersByTimeAsync(6000);
    expect(mocks.owner).toHaveBeenCalledOnce();
    pending.resolve(owned); await flush(); expect(mocks.write).toHaveBeenCalledTimes(2);
  });
  it("recovers queue processing after a failed ownership lookup", async () => {
    mocks.owner.mockRejectedValueOnce(new Error("offline"));
    stop = startSteamPerformanceOwnership(); await flush();
    expect(mocks.diagnostic).toHaveBeenCalledWith("control", { status: "ownership_unavailable" });
    await vi.advanceTimersByTimeAsync(2000); expect(mocks.write).toHaveBeenCalledTimes(2);
  });
});

function powerSettings() {
  const values: Record<string, unknown> = { steamos_tdp_limit: 15, steamos_tdp_limit_enabled: false,
    steamos_manual_gpu_clock_hz: 1600, steamos_manual_gpu_clock_enabled: false };
  const writes: Array<[string, unknown]> = [];
  vi.stubGlobal("window", { settingsStore: { GetClientSetting: (key: string) => [values[key], (value: unknown) => { writes.push([key, value]); }] } });
  mocks.owner.mockResolvedValue({ ...owned, owner: "steam", supported: true });
  return { values, writes };
}

describe("Steam power handoff", () => {
  it("reissues the existing numeric values before their enable flags, including false", async () => {
    const { writes } = powerSettings();
    expect(await reapplySteamPowerSettings("42", 42)).toBe(true);
    expect(writes).toEqual([["steamos_tdp_limit", 15], ["steamos_tdp_limit_enabled", false],
      ["steamos_manual_gpu_clock_hz", 1600], ["steamos_manual_gpu_clock_enabled", false]]);
  });
  it("does not reissue power settings on each poll or revision", async () => {
    const { writes } = powerSettings();
    stop = startSteamPerformanceOwnership(); await flush();
    expect(writes).toHaveLength(4);
    mocks.owner.mockResolvedValue({ ...owned, owner: "steam", supported: true, revision: 99 });
    await vi.advanceTimersByTimeAsync(6000);
    expect(writes).toHaveLength(4);
    mocks.owner.mockResolvedValue({ ...owned, owner: "pdc", supported: true });
    await vi.advanceTimersByTimeAsync(2000);
    mocks.owner.mockResolvedValue({ ...owned, owner: "steam", supported: true });
    await vi.advanceTimersByTimeAsync(2000);
    expect(writes).toHaveLength(8);
  });
  it.each([{ owner: "pdc", supported: true }, { owner: "steam", supported: false }])("requires supported Steam ownership %j", async (state) => {
    const { writes } = powerSettings();
    mocks.owner.mockResolvedValue({ ...owned, ...state });
    expect(await reapplySteamPowerSettings("42", 42)).toBe(false);
    expect(writes).toEqual([]);
  });
  it("does not enable a malformed setting or write an unconfirmed capability", async () => {
    const { writes, values } = powerSettings();
    values.steamos_tdp_limit = NaN; values.steamos_tdp_limit_enabled = true;
    mocks.capabilities.mockReturnValue({ is_tdp_limit_available: true });
    expect(await reapplySteamPowerSettings("42", 42)).toBe(false);
    expect(writes).toEqual([]);
  });
  it("checks stable and live context again between the value and enable writes", async () => {
    powerSettings();
    const setter = vi.fn(() => { mocks.game.mockReturnValue({ appid: "43", liveAppid: 43 }); });
    vi.stubGlobal("window", { settingsStore: { GetClientSetting: (key: string) => [key.endsWith("enabled") ? false : 15, setter] } });
    expect(await reapplySteamPowerSettings("42", 42)).toBe(true);
    expect(setter).toHaveBeenCalledExactlyOnceWith(15);
  });
});


describe("Steam power reapplication during an authorized reset", () => {
  it.each([false, true])("disables manual limits without replaying stale values while retaining PDC (global=%s)", async (global) => {
    const { writes, values } = powerSettings();
    Object.assign(values, { steamos_tdp_limit: 13, steamos_tdp_limit_enabled: true, steamos_manual_gpu_clock_hz: 800, steamos_manual_gpu_clock_enabled: true });
    const appid = global ? null : "42";
    const liveAppid = global ? null : 42;
    mocks.game.mockReturnValue(global ? null : game);
    mocks.owner.mockResolvedValue({ ...owned, owner: "pdc", context_appid: appid, reset_pending: true });
    expect(await reapplyResetPowerSettings(appid, liveAppid, () => true)).toBe(true);
    expect(writes).toEqual([["steamos_tdp_limit_enabled", false], ["steamos_manual_gpu_clock_enabled", false]]);
    expect(mocks.enable).not.toHaveBeenCalled();
  });

  it.each([
    { reset_pending: false }, { reset_pending: undefined }, { supported: false },
    { context_appid: "43" }, { owner: "unknown", reset_pending: false },
  ])("rejects absent or incompatible reset authority %j", async (state) => {
    const { writes } = powerSettings();
    mocks.owner.mockResolvedValue({ ...owned, owner: "pdc", reset_pending: true, ...state });
    expect(await reapplyResetPowerSettings("42", 42, () => true)).toBe(false);
    expect(writes).toEqual([]);
  });

  it("disables manual limits for an explicit Steam-owned reset without claiming PDC ownership", async () => {
    const { writes } = powerSettings();
    mocks.owner.mockResolvedValue({ ...owned, owner: "steam", explicit_owner: "steam", reset_pending: true });
    expect(await reapplyResetPowerSettings("42", 42, () => true)).toBe(true);
    expect(writes).toEqual([["steamos_tdp_limit_enabled", false], ["steamos_manual_gpu_clock_enabled", false]]);
    expect(mocks.enable).not.toHaveBeenCalled();
    expect(mocks.write).not.toHaveBeenCalled();
  });

  it("rejects a game change while reset authority is being read", async () => {
    const { writes } = powerSettings();
    const pending = deferred<Record<string, unknown>>();
    mocks.owner.mockReturnValue(pending.promise);
    const reset = reapplyResetPowerSettings("42", 42, () => true);
    await flush();
    mocks.game.mockReturnValue({ appid: "43", liveAppid: 43 });
    pending.resolve({ ...owned, owner: "pdc", reset_pending: true });
    expect(await reset).toBe(false);
    expect(writes).toEqual([]);
  });

  it("rejects an expired caller lease before reading authority", async () => {
    const { writes } = powerSettings();
    mocks.owner.mockResolvedValue({ ...owned, owner: "pdc", reset_pending: true });
    expect(await reapplyResetPowerSettings("42", 42, () => false)).toBe(false);
    expect(mocks.owner).not.toHaveBeenCalled();
    expect(writes).toEqual([]);
  });

  it("stops after the first setter if the caller lease expires during that setter", async () => {
    powerSettings();
    mocks.owner.mockResolvedValue({ ...owned, owner: "pdc", reset_pending: true });
    let current = true;
    const setter = vi.fn(() => { current = false; });
    vi.stubGlobal("window", { settingsStore: { GetClientSetting: (key: string) => [key.endsWith("enabled") ? false : 15, setter] } });
    expect(await reapplyResetPowerSettings("42", 42, () => current)).toBe(false);
    expect(setter).toHaveBeenCalledExactlyOnceWith(false);
  });

  it.each(["pdc", "steam"])("pauses normal reconciliation and handoff during reset (owner=%s)", async (owner) => {
    const { writes } = powerSettings();
    mocks.owner.mockResolvedValue({ ...owned, owner, reset_pending: true });
    mocks.profile.mockReturnValue("global");
    stop = startSteamPerformanceOwnership(); await flush();
    await vi.advanceTimersByTimeAsync(4000);
    expect(mocks.write).not.toHaveBeenCalled();
    expect(mocks.enable).not.toHaveBeenCalled();
    expect(writes).toEqual([]);
    mocks.owner.mockResolvedValue({ ...owned, owner, reset_pending: false });
    await vi.advanceTimersByTimeAsync(2000);
    if (owner === "steam") expect(writes).toHaveLength(4);
    else expect(mocks.enable).toHaveBeenCalledExactlyOnceWith(true);
  });
});


it.each(["setter", "value", "capability"])("validates both reset controls before writing when GPU %s is malformed", async (broken) => {
  powerSettings();
  mocks.owner.mockResolvedValue({ ...owned, owner: "pdc", reset_pending: true });
  const setter = vi.fn();
  if (broken === "capability") mocks.capabilities.mockReturnValue({ is_tdp_limit_available: true });
  vi.stubGlobal("window", { settingsStore: { GetClientSetting: (key: string) =>
    key === "steamos_manual_gpu_clock_enabled"
      ? [broken === "value" ? undefined : true, broken === "setter" ? undefined : setter]
      : [key.endsWith("enabled") ? true : 13, setter],
  } });
  expect(await reapplyResetPowerSettings("42", 42, () => true)).toBe(false);
  expect(setter).not.toHaveBeenCalled();
});

it("propagates a partial reset write failure so the caller aborts the lease", async () => {
  powerSettings();
  mocks.owner.mockResolvedValue({ ...owned, owner: "pdc", reset_pending: true });
  const tdp = vi.fn();
  const gpu = vi.fn().mockRejectedValue(new Error("GPU reset failed"));
  vi.stubGlobal("window", { settingsStore: { GetClientSetting: (key: string) =>
    [true, key === "steamos_tdp_limit_enabled" ? tdp : gpu],
  } });
  await expect(reapplyResetPowerSettings("42", 42, () => true)).rejects.toThrow("GPU reset failed");
  expect(tdp).toHaveBeenCalledExactlyOnceWith(false);
  expect(gpu).toHaveBeenCalledExactlyOnceWith(false);
});
