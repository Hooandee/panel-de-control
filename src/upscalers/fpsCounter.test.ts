// @vitest-environment happy-dom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
vi.mock("../tdp/runningGame", () => ({ readRunningGame: vi.fn() }));
import { readRunningGame } from "../tdp/runningGame";
import { fpsCounterSnapshot, startFpsCounterSession, syncFpsCounterSession, toggleFpsCounter } from "./fpsCounter";
beforeEach(() => { syncFpsCounterSession(null); vi.useFakeTimers(); });
afterEach(() => { vi.useRealTimers(); syncFpsCounterSession(null); });
it("keeps the previous switch position and reports a failed key", async () => {
  await toggleFpsCounter("1", async () => {});
  await toggleFpsCounter("1", async () => { throw new Error("no uinput"); });
  expect(fpsCounterSnapshot("1")).toEqual({ on: true, busy: false, failed: true });
});
it("ignores a late key response from a finished session and blocks duplicates", async () => {
  let finish!: () => void;
  const press = vi.fn(() => new Promise<void>((resolve) => { finish = resolve; }));
  const pending = toggleFpsCounter("1", press);
  await toggleFpsCounter("1", press);
  expect(press).toHaveBeenCalledTimes(1);
  syncFpsCounterSession(null);
  syncFpsCounterSession("1");
  finish(); await pending;
  expect(fpsCounterSnapshot("1")).toEqual({ on: false, busy: false, failed: false });
});
it("resets when the game ends while the QAM is closed, and stops on plugin unload", async () => {
  vi.mocked(readRunningGame).mockReturnValue({ appid: "shortcut-name", liveAppid: 42, name: "Game" });
  const stop = startFpsCounterSession();
  await toggleFpsCounter("42", async () => {});
  await vi.advanceTimersByTimeAsync(2000);
  expect(fpsCounterSnapshot("42").on).toBe(true);
  vi.mocked(readRunningGame).mockReturnValue(null);
  await vi.advanceTimersByTimeAsync(12000);
  expect(fpsCounterSnapshot("42").on).toBe(false);
  stop(); expect(vi.getTimerCount()).toBe(0);
});

it("keeps the counter through a brief moment without a running game (resume, focus change)", async () => {
  vi.mocked(readRunningGame).mockReturnValue({ appid: "7", liveAppid: 7, name: "Game" });
  const stop = startFpsCounterSession();
  await toggleFpsCounter("7", async () => {});
  vi.mocked(readRunningGame).mockReturnValue(null);
  await vi.advanceTimersByTimeAsync(4000);
  vi.mocked(readRunningGame).mockReturnValue({ appid: "7", liveAppid: 7, name: "Game" });
  await vi.advanceTimersByTimeAsync(2000);
  expect(fpsCounterSnapshot("7").on).toBe(true);
  stop();
});

it("remembers the counter when Panel reloads while the same game keeps running", async () => {
  vi.mocked(readRunningGame).mockReturnValue({ appid: "9", liveAppid: 9, name: "Game" });
  const stop = startFpsCounterSession();
  await toggleFpsCounter("9", async () => {});
  stop();
  vi.resetModules();
  const fresh = await import("./fpsCounter");
  const again = fresh.startFpsCounterSession();
  expect(fresh.fpsCounterSnapshot("9").on).toBe(true);
  vi.mocked(readRunningGame).mockReturnValue(null);
  await vi.advanceTimersByTimeAsync(12000);
  again();
  vi.resetModules();
  const later = await import("./fpsCounter");
  vi.mocked(readRunningGame).mockReturnValue({ appid: "9", liveAppid: 9, name: "Game" });
  const third = later.startFpsCounterSession();
  expect(later.fpsCounterSnapshot("9").on).toBe(false);
  third();
});
