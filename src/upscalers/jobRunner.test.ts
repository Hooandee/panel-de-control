import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LaunchReceipt } from "./launchOwnership";

vi.mock("./scalerTransition", () => ({ prepareScalerTransition: vi.fn(async () => null) }));
const state = { launch: "", job: null as unknown, receipt: null as LaunchReceipt | null };
vi.mock("../api", () => ({
  getUpscalersGame: vi.fn(async () => ({})),
  getUpscalersJob: vi.fn(async () => state.job),
  installUpscaler: vi.fn(async () => state.job),
  recordUpscalerArgs: vi.fn(async () => ({})),
  getUpscalerLaunchReceipt: vi.fn(async () => state.receipt),
  setUpscalerLaunchReceipt: vi.fn(async (_appid: string, _owner: string, receipt: LaunchReceipt) => { state.receipt = structuredClone(receipt); return true; }),
}));
vi.mock("../launch/steamApi", () => ({
  readAppDetails: vi.fn(async () => ({ launch: state.launch })),
  writeLaunchOptions: vi.fn((_id: number, value: string) => { state.launch = value; return true; }),
}));

import { onJobUpdate, readInstallRequest, startInstallJob, takeJobNotice, trackJob, waitForJobCompletion } from "./jobRunner";
import { transitionFrameGen } from "./frameGenTransition";
import { installUpscaler } from "../api";
import { readAppDetails } from "../launch/steamApi";
import type { UpscalerChoice } from "./types";

const game = { appid: "1", liveAppid: 1, isNonSteam: false };
beforeEach(() => { state.receipt = null; });

it.each(["download_failed", "cancelled"])("restores the prior generator only after the installation reports %s", async (error) => {
  vi.useFakeTimers();
  const id = `fg-transition-${error}`;
  state.job = { id, appid: "1", kind: "install", state: "running" };
  let priorEnabled = true;
  let settled = false;
  const transition = transitionFrameGen([
    { apply: async () => { priorEnabled = false; }, restore: async () => { priorEnabled = true; } },
    { apply: async () => {
      const started = await startInstallJob(game, { build: "fsr", quality: "native", sharpness: null });
      await waitForJobCompletion(started.id);
    }, restore: async () => {} },
  ]).then(() => { settled = true; }, () => { settled = true; });
  await vi.advanceTimersByTimeAsync(60_000);
  expect(settled).toBe(false);
  expect(priorEnabled).toBe(false);
  state.job = { ...(state.job as object), state: "error", error };
  await vi.advanceTimersByTimeAsync(300);
  await transition;
  expect(priorEnabled).toBe(true);
  vi.useRealTimers();
});

it("waits for launch confirmation and rejects when launch application fails", async () => {
  vi.useFakeTimers();
  state.job = { id: "fg-launch-fail", appid: "1", kind: "install", state: "running" };
  const started = await startInstallJob(game, { build: "fsr", quality: "native", sharpness: null });
  let outcome = "pending";
  const completed = waitForJobCompletion(started.id).then(() => { outcome = "done"; }, () => { outcome = "rejected"; });
  let release!: (value: Awaited<ReturnType<typeof readAppDetails>>) => void;
  vi.mocked(readAppDetails).mockImplementationOnce(() => new Promise((resolve) => { release = resolve; }));
  state.job = { ...(state.job as object), state: "done", result: { overrides: ["dxgi=n,b"], args: [] } };
  await vi.advanceTimersByTimeAsync(300);
  expect(outcome).toBe("pending");
  release(null);
  await vi.advanceTimersByTimeAsync(0);
  await completed;
  expect(outcome).toBe("rejected");
  vi.useRealTimers();
});

it("completes a generator transition after the matching job and launch write finish", async () => {
  vi.useFakeTimers();
  state.launch = "%command%";
  state.job = { id: "fg-launch-success", appid: "1", kind: "install", state: "running" };
  const started = await startInstallJob(game, { build: "fsr", quality: "native", sharpness: null });
  let complete = false;
  const waiting = waitForJobCompletion(started.id).then(() => { complete = true; });
  await vi.advanceTimersByTimeAsync(300);
  expect(complete).toBe(false);
  state.job = { ...(state.job as object), state: "done", result: { overrides: ["dxgi=n,b"], args: [] } };
  await vi.advanceTimersByTimeAsync(300);
  await waiting;
  expect(complete).toBe(true);
  expect(state.launch).toContain("dxgi=n,b");
  vi.useRealTimers();
});

describe("jobRunner", () => {
  afterEach(() => vi.useRealTimers());

  it("writes launch options when the job ends, with nobody watching", async () => {
    vi.useFakeTimers();
    state.launch = "";
    state.job = { id: "a", appid: "1", kind: "install", state: "done", result: { overrides: ["dxgi=n,b"], args: [] } };
    trackJob({ id: "a", appid: "1", kind: "install", state: "running" } as never, game);
    await vi.advanceTimersByTimeAsync(300);
    expect(state.launch).toContain("dxgi=n,b");
  });

  it("takes the old install's entries out when a switch fails midway", async () => {
    vi.useFakeTimers();
    state.launch = 'WINEDLLOVERRIDES="dxgi=n,b" %command%';
    state.job = { id: "b", appid: "1", kind: "install", state: "error", error: "helixsr_failed",
      leftover: { removed_overrides: ["dxgi=n,b"], removed_args: [], env: {} } };
    const updates: unknown[] = [];
    const stop = onJobUpdate((u) => updates.push(u));
    trackJob({ id: "b", appid: "1", kind: "install", state: "running" } as never, game);
    await vi.advanceTimersByTimeAsync(300);
    stop();
    expect(state.launch).not.toContain("dxgi");
    expect(updates).toHaveLength(1);
  });
});

it("keeps custom Proton variables and Mako arguments through a completed install", async () => {
  vi.useFakeTimers();
  const original = 'FSR4_UPGRADE="custom" ~/.local/bin/mako-run --preset quality %command% -dx12';
  state.launch = original;
  state.job = { id: "owned-custom", appid: "1", kind: "install", state: "done", result: { overrides: [], args: [], env: { FSR4_UPGRADE: "1" } } };
  trackJob({ id: "owned-custom", appid: "1", kind: "install", state: "running" } as never, game);
  await vi.advanceTimersByTimeAsync(300);
  expect(state.launch).toBe(original);
  expect(state.receipt?.env).toEqual([]);
  vi.useRealTimers();
});

it("removes only the confirmed owned env on uninstall, retaining later user edits", async () => {
  vi.useFakeTimers();
  state.launch = "%command% -dx12";
  state.job = { id: "owned-install", appid: "1", kind: "install", state: "done", result: { overrides: [], args: [], env: { FSR4_UPGRADE: "1" } } };
  trackJob({ id: "owned-install", appid: "1", kind: "install", state: "running" } as never, game);
  await vi.advanceTimersByTimeAsync(300);
  expect(state.receipt?.env).toEqual([{ name: "FSR4_UPGRADE", before: null, applied: "1" }]);
  state.launch = state.launch.replace("FSR4_UPGRADE=1", 'FSR4_UPGRADE="custom"');
  state.job = { id: "owned-uninstall", appid: "1", kind: "uninstall", state: "done", result: { overrides: [], args: [], env: { FSR4_UPGRADE: null } } };
  trackJob({ id: "owned-uninstall", appid: "1", kind: "uninstall", state: "running" } as never, game);
  await vi.advanceTimersByTimeAsync(300);
  expect(state.launch).toBe('FSR4_UPGRADE="custom" %command% -dx12');
  vi.useRealTimers();
});


it("retains the exact install request through remount and error, then clears it on success", async () => {
  vi.useFakeTimers();
  const requested: UpscalerChoice = { build: "fsr-4.0.2c", quality: "balanced", sharpness: "soft", model: null,
    fg: "off", fg_route: null, confirm_anti_cheat: true, env: "TEST=1" };
  const expected = { ...requested };
  const target = { appid: "retry-game", liveAppid: 99, isNonSteam: true };
  state.job = { id: "retry-a", appid: target.appid, kind: "install", state: "running" };
  const started = await startInstallJob(target, requested);
  requested.build = "fsr-4.1.1";
  trackJob(started, target);
  expect(readInstallRequest(target.appid, started.id)).toEqual(expected);
  const returned = readInstallRequest(target.appid)!;
  returned.build = "xess";
  state.job = { ...started, state: "error", error: "download_failed" };
  await vi.advanceTimersByTimeAsync(300);
  expect(readInstallRequest(target.appid, started.id)).toEqual(expected);
  state.job = { ...started, id: "retry-b", state: "running" };
  const retried = await startInstallJob(target, readInstallRequest(target.appid, started.id)!);
  expect(installUpscaler).toHaveBeenLastCalledWith(target.appid, expected);
  expect(readInstallRequest(target.appid, started.id)).toBeNull();
  state.job = { ...retried, state: "done" };
  await vi.advanceTimersByTimeAsync(300);
  expect(readInstallRequest(target.appid)).toBeNull();
  vi.useRealTimers();
});

it("isolates games and invalidates a request when an unrelated replacement job starts", async () => {
  vi.useFakeTimers();
  const first = { appid: "first", liveAppid: 100, isNonSteam: false };
  const second = { appid: "second", liveAppid: 101, isNonSteam: false };
  const choice: UpscalerChoice = { build: "fsr-4.0.2c", quality: "native", sharpness: null };
  state.job = { id: "first-a", appid: first.appid, kind: "install", state: "running" };
  const a = await startInstallJob(first, choice);
  state.job = { ...a, state: "error", error: "download_failed" };
  await vi.advanceTimersByTimeAsync(300);
  state.job = { ...a, id: "second-a", appid: second.appid, state: "running" };
  const b = await startInstallJob(second, choice);
  state.job = { ...b, state: "error", error: "download_failed" };
  await vi.advanceTimersByTimeAsync(300);
  expect(readInstallRequest(first.appid, a.id)).toEqual(choice);
  expect(readInstallRequest(second.appid, a.id)).toBeNull();
  const replacement = { ...a, id: "first-b", kind: "uninstall" as const };
  trackJob(replacement, first);
  expect(readInstallRequest(first.appid)).toBeNull();
  expect(readInstallRequest(second.appid, b.id)).toEqual(choice);
  state.job = { ...replacement, state: "done" };
  await vi.advanceTimersByTimeAsync(300);
  vi.useRealTimers();
});


it("does not clear a newer request when the old job finishes writing launch options", async () => {
  vi.useFakeTimers();
  const target = { appid: "late-finish", liveAppid: 102, isNonSteam: false };
  const firstChoice: UpscalerChoice = { build: "fsr-4.0.2c", quality: "native", sharpness: null };
  const secondChoice = { ...firstChoice, build: "xess" };
  state.job = { id: "late-a", appid: target.appid, kind: "install", state: "running" };
  const first = await startInstallJob(target, firstChoice);
  let finish!: (value: Awaited<ReturnType<typeof readAppDetails>>) => void;
  vi.mocked(readAppDetails).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  state.job = { ...first, state: "done", result: { overrides: [], args: [] } };
  await vi.advanceTimersByTimeAsync(300);
  state.job = { ...first, id: "late-b", state: "running" };
  const second = await startInstallJob(target, secondChoice);
  finish(null);
  await Promise.resolve();
  await Promise.resolve();
  expect(readInstallRequest(target.appid, second.id)).toEqual(secondChoice);
  state.job = { ...second, state: "done" };
  await vi.advanceTimersByTimeAsync(300);
  expect(readInstallRequest(target.appid)).toBeNull();
  vi.useRealTimers();
});

it("keeps a closing launch notice for a page opened later, once, until the game's next job", async () => {
  vi.useFakeTimers();
  const target = { appid: "unseen-notice", liveAppid: 103, isNonSteam: false };
  state.job = { id: "unseen-a", appid: target.appid, kind: "install", state: "done", result: { overrides: ["dxgi=n,b"], args: [] } };
  vi.mocked(readAppDetails).mockResolvedValueOnce(null);
  trackJob({ id: "unseen-a", appid: target.appid, kind: "install", state: "running" } as never, target);
  await vi.advanceTimersByTimeAsync(300);
  expect(takeJobNotice(target.appid)).toEqual({ key: "up.launch.failed", params: { value: expect.stringContaining("dxgi=n,b") } });
  expect(takeJobNotice(target.appid)).toBeNull();
  vi.mocked(readAppDetails).mockResolvedValueOnce(null);
  state.job = { id: "unseen-b", appid: target.appid, kind: "install", state: "done", result: { overrides: ["dxgi=n,b"], args: [] } };
  trackJob({ id: "unseen-b", appid: target.appid, kind: "install", state: "running" } as never, target);
  await vi.advanceTimersByTimeAsync(300);
  trackJob({ id: "unseen-c", appid: target.appid, kind: "uninstall", state: "running" } as never, target);
  expect(takeJobNotice(target.appid)).toBeNull();
  state.job = { id: "unseen-c", appid: target.appid, kind: "uninstall", state: "done" };
  await vi.advanceTimersByTimeAsync(300);
  vi.useRealTimers();
});
