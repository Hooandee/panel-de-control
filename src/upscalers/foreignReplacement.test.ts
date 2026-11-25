import { expect, it, vi } from "vitest";
import { replaceForeignInstallation } from "./foreignReplacement";
import type { UpscalerJob } from "./types";

const job = { id: 1, state: "running" } as unknown as UpscalerJob;

it("tracks the replacement before refreshing, even if refresh fails", async () => {
  const order: string[] = [];
  const track = vi.fn();
  await expect(replaceForeignInstallation(
    async () => { order.push("adopt"); },
    async () => { order.push("install"); return job; },
    async (run) => { track(await run()); order.push("track"); },
    async () => { order.push("refresh"); throw new Error("refresh"); },
  )).rejects.toThrow("refresh");
  expect(track).toHaveBeenCalledExactlyOnceWith(job);
  expect(order).toEqual(["adopt", "install", "track", "refresh"]);
});

it("refreshes the recoverable backup after the job runner reports an installation failure", async () => {
  const error = new Error("download_failed");
  const report = vi.fn();
  const refresh = vi.fn(async () => undefined);
  await replaceForeignInstallation(
    async () => undefined,
    async () => { throw error; },
    async (run) => { try { await run(); } catch (caught) { report(caught); } },
    refresh,
  );
  expect(report).toHaveBeenCalledExactlyOnceWith(error);
  expect(refresh).toHaveBeenCalledOnce();
});

it("does not install when adoption fails", async () => {
  const install = vi.fn(async () => job);
  await replaceForeignInstallation(
    async () => { throw new Error("running"); }, install,
    async (run) => { await run().catch(() => undefined); }, async () => undefined,
  );
  expect(install).not.toHaveBeenCalled();
});
