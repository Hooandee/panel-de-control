import { expect, it, vi } from "vitest";
import type { JobNotice, JobUpdate } from "./jobRunner";

const runner = vi.hoisted(() => ({ listeners: new Set<(update: JobUpdate) => void>(), notices: {} as Record<string, JobNotice> }));
vi.mock("../api", () => ({ uninstallUpscaler: vi.fn() }));
vi.mock("./jobRunner", () => ({
  startInstallJob: vi.fn(async (game: { appid: string }) => ({ id: `job-${game.appid}`, appid: game.appid, kind: "install", state: "running" })),
  onJobUpdate: (listener: (update: JobUpdate) => void) => { runner.listeners.add(listener); return () => runner.listeners.delete(listener); },
  trackJob: (job: { id: string; appid: string }) => {
    const update = { job: { ...job, state: "done", result: {} }, finished: true, notice: runner.notices[job.appid] ?? null } as JobUpdate;
    queueMicrotask(() => [...runner.listeners].forEach((listener) => listener(update)));
  },
}));

import { runBulk } from "./bulk";
import type { GameEntry } from "../launch/steamApi";

const step = (id: number, name: string) => ({
  game: { liveAppid: id, name, isNonSteam: false } as unknown as GameEntry,
  choice: { build: "fsr", quality: null, sharpness: null },
});

it("counts a finished install as done only when its launch options were written", async () => {
  runner.notices = { "2": { key: "up.launch.failed", params: { value: "x" } }, "3": { key: "up.kept", params: { count: 1 } } };
  const result = await runBulk("install", [step(1, "Clean"), step(2, "Unwritten"), step(3, "Kept")], () => undefined);
  expect(result.done).toBe(2);
  expect(result.skipped).toEqual([{ name: "Unwritten", reason: "launch_failed" }]);
});
