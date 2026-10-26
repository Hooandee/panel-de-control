import { afterEach, beforeEach, expect, it, vi } from "vitest";
const rpc = vi.hoisted(() => ({ begin: vi.fn(), finish: vi.fn(), abort: vi.fn(), power: vi.fn(), changed: () => {} }));
vi.mock("../api", () => ({ beginGamePowerReset: rpc.begin, finishGamePowerReset: rpc.finish, abortGamePowerReset: rpc.abort }));
vi.mock("./performanceOwnership", () => ({ reapplyResetPowerSettings: rpc.power }));
vi.mock("./performanceRuntime", () => ({ subscribeSteamPerformanceState: (fn: () => void) => { rpc.changed = fn; return () => { rpc.changed = () => {}; }; } }));
import { resetManagedGamePerformance } from "./performanceReset";
import type { GamePowerOwnerState } from "../api";
import type { PerformanceSettingsDeps } from "./performanceSettings";
const owner = { context_appid: "42", revision: 3, owner: "pdc", explicit_owner: "pdc", supported: true } as GamePowerOwnerState;
let store: any;
let deps: PerformanceSettingsDeps;
let current: boolean;
beforeEach(() => {
  vi.useFakeTimers(); vi.resetAllMocks(); current = true;
  rpc.begin.mockResolvedValue({ ...owner, ok: true, token: "reset-token" });
  rpc.power.mockResolvedValue(true);
  rpc.finish.mockResolvedValue({ ...owner, ok: true }); rpc.abort.mockResolvedValue({ ok: true });
  store = { nCurrentGameID: "42", nActiveProfileGameID: "42", msgSettingsPerApp: { split_scaling_filter: 3 }, msgLimits: { split_scaling_filters_available: [1, 3] }, SetSplitScalingFilter: vi.fn(), ResetCurrentPerfProfileSettings: vi.fn() };
  deps = { store: () => store, runningGameId: () => 42, display: () => null, gamescope: () => null, steamOs: () => null };
});
afterEach(() => vi.useRealTimers());
const run = () => resetManagedGamePerformance(deps, { scope: "game", runningGameId: 42 }, owner, () => current);
it("waits for fresh Steam settings and saves reset values without transferring ownership", async () => {
  const pending = run(); await vi.advanceTimersByTimeAsync(0);
  expect(store.ResetCurrentPerfProfileSettings).toHaveBeenCalledOnce();
  await vi.advanceTimersByTimeAsync(500);
  expect(rpc.finish).not.toHaveBeenCalled();
  store.msgSettingsPerApp.split_scaling_filter = 1; rpc.changed();
  await vi.advanceTimersByTimeAsync(350); await pending;
  expect(rpc.finish).toHaveBeenCalledExactlyOnceWith("reset-token", { splitScalingFilter: 1 });
  expect(rpc.abort).not.toHaveBeenCalled();
  expect(rpc.power).toHaveBeenCalledOnce();
});
it("aborts when no reset readback arrives instead of saving the previous values", async () => {
  const pending = expect(run()).rejects.toThrow("reset_readback_timeout");
  await vi.advanceTimersByTimeAsync(5050); await pending;
  expect(rpc.finish).not.toHaveBeenCalled(); expect(rpc.abort).toHaveBeenCalledWith("reset-token");
});
it("aborts after a game switch before committing a reset", async () => {
  const pending = expect(run()).rejects.toThrow("stale_context");
  await vi.advanceTimersByTimeAsync(0); current = false;
  await vi.advanceTimersByTimeAsync(50); await pending;
  expect(rpc.finish).not.toHaveBeenCalled(); expect(rpc.abort).toHaveBeenCalledOnce();
});
it("aborts when the native reset or persistence fails", async () => {
  store.ResetCurrentPerfProfileSettings.mockImplementation(() => { throw new Error("native_failure"); });
  await expect(run()).rejects.toThrow("failed");
  expect(rpc.finish).not.toHaveBeenCalled(); expect(rpc.abort).toHaveBeenCalledOnce();
});
it("does not start a lease when reset is unavailable", async () => {
  delete store.ResetCurrentPerfProfileSettings;
  await expect(run()).rejects.toThrow("reset_unavailable"); expect(rpc.begin).not.toHaveBeenCalled();
});
