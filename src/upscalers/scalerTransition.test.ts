import { beforeEach, expect, it, vi } from "vitest";
const api = vi.hoisted(() => ({ beginScalerTransition: vi.fn(), finishScalerTransition: vi.fn(), getMakoStatus: vi.fn() }));
vi.mock("../api", () => api);
vi.mock("./makoProfile", () => ({ saveMakoProfile: vi.fn() }));
vi.mock("./managedLaunch", () => ({ applyManagedLaunch: vi.fn() }));
import { prepareScalerTransition, scalerSwitching } from "./scalerTransition";
import { saveMakoProfile } from "./makoProfile";
import { applyManagedLaunch } from "./managedLaunch";
const game = { appid: "1", liveAppid: 1, isNonSteam: false };
const previous = { enabled: true, scaling_enabled: true, multiplier: 3, scaling_sharpness: 0.4 };
beforeEach(() => {
  vi.resetAllMocks();
  api.getMakoStatus.mockResolvedValue({ profiles: { "1": previous } });
  api.beginScalerTransition.mockResolvedValue({ token: "snapshot", restore: null, recovery: false, previous_mako: previous });
  api.finishScalerTransition.mockResolvedValue(null);
  vi.mocked(saveMakoProfile).mockResolvedValue(null);
  vi.mocked(applyManagedLaunch).mockResolvedValue({ ok: true, preserved: { env: [], wrappers: [] } });
});
it("disables spatial scaling only and commits after the caller confirms installation", async () => {
  const change = await prepareScalerTransition(game, "installed");
  expect(saveMakoProfile).toHaveBeenCalledWith("1", 1, { scaling_enabled: false }, false);
  expect(scalerSwitching("1")).toBe(true);
  expect(api.finishScalerTransition).not.toHaveBeenCalled();
  await change!.finish(true);
  expect(api.finishScalerTransition).toHaveBeenCalledWith("1", "snapshot", false);
  expect(scalerSwitching("1")).toBe(false);
});
it("leaves Mako FG alone untouched when installing an upscaler", async () => {
  api.getMakoStatus.mockResolvedValue({ profiles: { "1": { ...previous, scaling_enabled: false } } });
  expect(await prepareScalerTransition(game, "installed")).toBeNull();
  expect(api.beginScalerTransition).not.toHaveBeenCalled();
  expect(saveMakoProfile).not.toHaveBeenCalled();
});
it("restores files, owned launch changes and the complete Mako profile on failure", async () => {
  api.finishScalerTransition.mockResolvedValueOnce({ overrides: ["dxgi=n,b"], args: ["-dx11"], removed_overrides: ["version=n,b"], removed_args: ["-new"], env: {} });
  const change = await prepareScalerTransition(game, "installed");
  await change!.finish(false);
  const options = vi.mocked(applyManagedLaunch).mock.calls[0][4]!;
  const restored = options.transform!('MANGOHUD=1 WINEDLLOVERRIDES="version=n,b" %command% -new -user');
  expect(restored).toContain("MANGOHUD=1");
  expect(restored).toContain("-user");
  expect(restored).toContain("-dx11");
  expect(restored).not.toContain("-new");
  expect(restored).not.toContain("version=n,b");
  expect(saveMakoProfile).toHaveBeenLastCalledWith("1", 1, previous, false);
  expect(api.finishScalerTransition).toHaveBeenLastCalledWith("1", "snapshot", false);
});
it("retains the checkpoint when launch restoration cannot be confirmed", async () => {
  api.finishScalerTransition.mockResolvedValue({ overrides: ["dxgi=n,b"], args: [] });
  vi.mocked(applyManagedLaunch).mockResolvedValue({ ok: false, pending: true, preserved: { env: [], wrappers: [] } });
  const change = await prepareScalerTransition(game, "mako");
  await expect(change!.finish(false)).rejects.toThrow("transition_restore_failed");
  expect(api.finishScalerTransition).toHaveBeenCalledTimes(1);
  expect(api.finishScalerTransition).toHaveBeenLastCalledWith("1", "snapshot", true);
  expect(scalerSwitching("1")).toBe(false);
});
it("rejects overlapping changes for the same game", async () => {
  const change = await prepareScalerTransition(game, "mako");
  await expect(prepareScalerTransition(game, "installed")).rejects.toThrow("busy");
  await change!.finish(true);
});

it("recovers an interrupted transition from the persisted profile before allowing another change", async () => {
  const original = { ...previous, multiplier: 4 };
  api.beginScalerTransition.mockResolvedValue({ token: "snapshot", recovery: true, previous_mako: original });
  await expect(prepareScalerTransition(game, "mako")).rejects.toThrow("transition_recovered");
  expect(api.finishScalerTransition).toHaveBeenNthCalledWith(1, "1", "snapshot", true);
  expect(saveMakoProfile).toHaveBeenLastCalledWith("1", 1, original, false);
  expect(api.finishScalerTransition).toHaveBeenLastCalledWith("1", "snapshot", false);
  expect(scalerSwitching("1")).toBe(false);
});

it("recovers a pending install transition even if spatial Mako is already disabled", async () => {
  api.getMakoStatus.mockResolvedValue({ profiles: { "1": { ...previous, scaling_enabled: false } }, scaler_transition_pending: true });
  api.beginScalerTransition.mockResolvedValue({ token: "snapshot", recovery: true, previous_mako: previous });
  await expect(prepareScalerTransition(game, "installed")).rejects.toThrow("transition_recovered");
  expect(saveMakoProfile).toHaveBeenLastCalledWith("1", 1, previous, false);
});
it("never claims the previous upscaler came back when HelixSR left as the switch began", async () => {
  api.beginScalerTransition.mockResolvedValue({ token: "snapshot", restore: null, recovery: false, previous_mako: previous, helix_removed: true });
  api.finishScalerTransition.mockRejectedValueOnce(new Error("transition_conflict")).mockResolvedValue(null);
  const change = await prepareScalerTransition(game, "installed", true);
  expect(change!.previousRemoved).toBe(true);
  await expect(change!.finish(true)).rejects.toThrow("transition_failed_clean");
});
