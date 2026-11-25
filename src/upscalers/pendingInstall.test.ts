import { afterEach, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  running: 777 as number | null, installs: [] as unknown[], fail: [] as string[], hold: false, release: [] as (() => void)[],
}));
vi.mock("../tdp/runningGame", () => ({ readRunningGame: () => state.running === null ? null : { appid: String(state.running), liveAppid: state.running, name: "Game" } }));
vi.mock("./jobRunner", () => ({
  startInstallJob: vi.fn(async (_game, choice) => {
    const code = state.fail.shift();
    if (code) throw new Error(code);
    state.installs.push(choice);
    return { id: `job-${state.installs.length}`, appid: "777", kind: "install", state: "running" };
  }),
  trackJob: vi.fn(),
  waitForJobCompletion: vi.fn(() => state.hold ? new Promise<void>((resolve) => { state.release.push(resolve); }) : Promise.resolve()),
}));
vi.mock("./errorCode", () => ({ upscalerErrorCode: (error: Error) => error.message }));

import { cancelPendingInstall, holdForRestart, pendingInstall, queueForGameExit, runPendingInstall, takePendingFailure } from "./pendingInstall";

const game = { appid: "777", liveAppid: 777, isNonSteam: false };
const other = { appid: "888", liveAppid: 888, isNonSteam: false };
const choice = { build: "fsr-3.1", quality: "quality", sharpness: null, model: null } as never;
afterEach(async () => {
  cancelPendingInstall("777");
  cancelPendingInstall("888");
  takePendingFailure("777");
  state.release.splice(0).forEach((resolve) => resolve());
  state.installs = [];
  state.fail = [];
  state.hold = false;
  state.running = 777;
  vi.useRealTimers();
  await new Promise((resolve) => setTimeout(resolve, 0));
});

it("installs the version chosen while playing once the game closes", async () => {
  vi.useFakeTimers();
  queueForGameExit(game, choice);
  await vi.advanceTimersByTimeAsync(4000);
  expect(state.installs).toEqual([]);
  state.running = null;
  await vi.advanceTimersByTimeAsync(2100);
  expect(state.installs).toEqual([choice]);
  expect(pendingInstall("777")).toBeNull();
});

it("keeps the choice through passing failures and reports a final one", async () => {
  vi.useFakeTimers();
  queueForGameExit(game, choice);
  state.running = null;
  state.fail = ["running", "busy"];
  await vi.advanceTimersByTimeAsync(2100);
  expect(pendingInstall("777")).toEqual(choice);
  await vi.advanceTimersByTimeAsync(2100);
  expect(pendingInstall("777")).toEqual(choice);
  await vi.advanceTimersByTimeAsync(2100);
  expect(state.installs).toEqual([choice]);
  queueForGameExit(game, choice);
  state.fail = ["unsupported_gpu"];
  await vi.advanceTimersByTimeAsync(2100);
  expect(pendingInstall("777")).toBeNull();
  expect(takePendingFailure("777")).toBe("unsupported_gpu");
});

it("installs queued games one at a time", async () => {
  vi.useFakeTimers();
  state.running = null;
  state.hold = true;
  queueForGameExit(game, choice);
  queueForGameExit(other, choice);
  await vi.advanceTimersByTimeAsync(4100);
  expect(state.installs).toHaveLength(1);
  state.release.shift()?.();
  await vi.advanceTimersByTimeAsync(2100);
  expect(state.installs).toHaveLength(2);
});

it("a restart keeps the watcher away and installs before the game opens", async () => {
  vi.useFakeTimers();
  queueForGameExit(game, choice);
  const release = holdForRestart("777");
  state.running = null;
  await vi.advanceTimersByTimeAsync(4100);
  expect(state.installs).toEqual([]);
  await runPendingInstall("777");
  release();
  expect(state.installs).toEqual([choice]);
});

it("a restart whose install fails because the game is still closing keeps the choice", async () => {
  queueForGameExit(game, choice);
  const release = holdForRestart("777");
  state.fail = ["running"];
  await expect(runPendingInstall("777")).rejects.toThrow("running");
  release();
  expect(pendingInstall("777")).toEqual(choice);
});
