import { afterEach, describe, expect, it, vi } from "vitest";

const state = { launch: "", job: null as unknown };
vi.mock("../api", () => ({
  getUpscalersJob: vi.fn(async () => state.job),
  recordUpscalerArgs: vi.fn(async () => ({})),
}));
vi.mock("../launch/steamApi", () => ({
  readAppDetails: vi.fn(async () => ({ launch: state.launch })),
  writeLaunchOptions: vi.fn((_id: number, value: string) => { state.launch = value; return true; }),
}));

import { onJobUpdate, trackJob } from "./jobRunner";

const game = { appid: "1", liveAppid: 1, isNonSteam: false };

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
