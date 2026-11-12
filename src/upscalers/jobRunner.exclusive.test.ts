import { afterEach, beforeEach, expect, it, vi } from "vitest";
const mocks = vi.hoisted(() => ({
  getUpscalersGame: vi.fn(), getUpscalersJob: vi.fn(), installUpscaler: vi.fn(), uninstallUpscaler: vi.fn(),
  recordUpscalerArgs: vi.fn(), prepareScalerTransition: vi.fn(), saveMakoProfile: vi.fn(), applyManagedLaunch: vi.fn(), finish: vi.fn(),
}));
vi.mock("../api", () => mocks);
vi.mock("./scalerTransition", () => mocks);
vi.mock("./makoProfile", () => mocks);
vi.mock("./managedLaunch", () => mocks);
import { saveExclusiveMakoProfile, startInstallJob, waitForJobCompletion } from "./jobRunner";
const game = { appid: "1462040", liveAppid: 1462040, isNonSteam: false };
let job: any;
beforeEach(() => {
  vi.resetAllMocks(); vi.useFakeTimers();
  job = { id: crypto.randomUUID(), appid: game.appid, kind: "uninstall", state: "running" };
  mocks.getUpscalersGame.mockResolvedValue({ install: { build: "fsr" }, analysis: { foreign: false } });
  mocks.prepareScalerTransition.mockResolvedValue({ finish: mocks.finish });
  mocks.getUpscalersJob.mockImplementation(async () => job);
  mocks.uninstallUpscaler.mockImplementation(async () => job);
  mocks.installUpscaler.mockImplementation(async () => job);
  mocks.recordUpscalerArgs.mockResolvedValue({});
  mocks.applyManagedLaunch.mockImplementation(async (_app, _live, _owner, _desired, options) => {
    options.transform?.("%command%");
    await options.beforeApply?.();
    return { ok: true, preserved: { env: [], wrappers: [] } };
  });
});
afterEach(() => vi.useRealTimers());
it("retires the managed scaler and confirms launch before activating spatial Mako", async () => {
  const request = { scaling_enabled: true, scaling_factor: 1.5, scaling_sharpness: 0.8 };
  const result = saveExclusiveMakoProfile(game, request);
  await vi.advanceTimersByTimeAsync(0);
  expect(mocks.uninstallUpscaler).toHaveBeenCalledWith(game.appid);
  expect(mocks.saveMakoProfile).not.toHaveBeenCalled();
  job = { ...job, state: "done", result: { overrides: ["dxgi=n,b"], args: [] } };
  await vi.advanceTimersByTimeAsync(250);
  await result;
  expect(mocks.saveMakoProfile).toHaveBeenCalledWith(game.appid, game.liveAppid, request, false);
  expect(mocks.finish).toHaveBeenCalledWith(true);
});
it("restores the checkpoint when activation fails after uninstall", async () => {
  mocks.saveMakoProfile.mockRejectedValue(new Error("launch_failed"));
  const result = saveExclusiveMakoProfile(game, { scaling_enabled: true }).catch(error => error.message);
  await vi.advanceTimersByTimeAsync(0);
  job = { ...job, state: "done", result: { overrides: [], args: [] } };
  await vi.advanceTimersByTimeAsync(250);
  expect(await result).toBe("launch_failed");
  expect(mocks.finish).toHaveBeenCalledWith(false);
});
it("does not activate Mako over retained modified files", async () => {
  const result = saveExclusiveMakoProfile(game, { scaling_enabled: true }).catch(error => error.message);
  await vi.advanceTimersByTimeAsync(0);
  job = { ...job, state: "done", result: { overrides: [], args: [], kept: ["dxgi.dll"] } };
  await vi.advanceTimersByTimeAsync(250);
  expect(await result).toBe("foreign");
  expect(mocks.saveMakoProfile).not.toHaveBeenCalled();
  expect(mocks.finish).toHaveBeenCalledWith(false);
});
it("leaves manually installed upscalers alone", async () => {
  mocks.getUpscalersGame.mockResolvedValue({ install: null, analysis: { foreign: true } });
  await expect(saveExclusiveMakoProfile(game, { scaling_enabled: true })).rejects.toThrow("foreign");
  expect(mocks.prepareScalerTransition).not.toHaveBeenCalled();
  expect(mocks.uninstallUpscaler).not.toHaveBeenCalled();
});
it("does not finish the install transition until launch confirmation succeeds", async () => {
  job.kind = "install";
  const started = await startInstallJob(game, { build: "fsr", quality: "native", sharpness: null });
  const completed = waitForJobCompletion(started.id).catch(error => error.message);
  mocks.applyManagedLaunch.mockResolvedValue({ ok: false });
  job = { ...job, state: "done", result: { overrides: ["dxgi=n,b"], args: [] } };
  await vi.advanceTimersByTimeAsync(250);
  expect(await completed).toBe("transition_failed");
  expect(mocks.finish).toHaveBeenCalledWith(false);
});

it("records ownership before launch application and rolls back if that record fails", async () => {
  job.kind = "install";
  let written = false;
  mocks.recordUpscalerArgs.mockRejectedValue(new Error("unavailable"));
  mocks.applyManagedLaunch.mockImplementation(async (_app, _live, _owner, _desired, options) => {
    options.transform("%command% -user");
    await options.beforeApply();
    written = true;
    return { ok: true };
  });
  const started = await startInstallJob(game, { build: "fsr", quality: "native", sharpness: null });
  const completed = waitForJobCompletion(started.id).catch(error => error.message);
  job = { ...job, state: "done", result: { overrides: ["dxgi=n,b"], args: ["-dx11"] } };
  await vi.advanceTimersByTimeAsync(250);
  expect(await completed).toBe("transition_failed");
  expect(written).toBe(false);
  expect(mocks.recordUpscalerArgs).toHaveBeenCalledWith(game.appid, ["-dx11"], ["dxgi=n,b"], []);
  expect(mocks.finish).toHaveBeenCalledWith(false);
});

it("does not uninstall again what opening the transition already took out (HelixSR)", async () => {
  mocks.getUpscalersGame.mockResolvedValueOnce({ install: { build: "hlx-fsr4", engine: "helixsr" }, analysis: { foreign: false } })
    .mockResolvedValueOnce({ install: null, analysis: { foreign: false } });
  const request = { scaling_enabled: true };
  await saveExclusiveMakoProfile(game, request);
  expect(mocks.uninstallUpscaler).not.toHaveBeenCalled();
  expect(mocks.saveMakoProfile).toHaveBeenCalledWith(game.appid, game.liveAppid, request, false);
});

it("says HelixSR is gone when spatial Mako fails after the switch took it out", async () => {
  mocks.getUpscalersGame.mockResolvedValueOnce({ install: { build: "hlx-fsr4", engine: "helixsr" }, analysis: { foreign: false } })
    .mockResolvedValueOnce({ install: null, analysis: { foreign: false } });
  mocks.prepareScalerTransition.mockResolvedValue({ finish: mocks.finish, previousRemoved: true });
  mocks.saveMakoProfile.mockRejectedValue(new Error("launch_failed"));
  await expect(saveExclusiveMakoProfile(game, { scaling_enabled: true })).rejects.toThrow("transition_failed_clean");
  expect(mocks.finish).toHaveBeenCalledWith(false);
});
it("says HelixSR is gone when an install that took it out ends in an error", async () => {
  job.kind = "install";
  mocks.prepareScalerTransition.mockResolvedValue({ finish: mocks.finish, previousRemoved: true });
  const started = await startInstallJob(game, { build: "fsr", quality: "native", sharpness: null });
  const completed = waitForJobCompletion(started.id).catch(error => error.message);
  job = { ...job, state: "error", error: "download_failed" };
  await vi.advanceTimersByTimeAsync(250);
  expect(await completed).toBe("transition_failed_clean");
  expect(mocks.finish).toHaveBeenCalledWith(false);
});
it("says HelixSR is gone when the install cannot even start after taking it out", async () => {
  mocks.prepareScalerTransition.mockResolvedValue({ finish: mocks.finish, previousRemoved: true });
  mocks.installUpscaler.mockRejectedValue(new Error("busy"));
  await expect(startInstallJob(game, { build: "fsr", quality: "native", sharpness: null })).rejects.toThrow("transition_failed_clean");
});
