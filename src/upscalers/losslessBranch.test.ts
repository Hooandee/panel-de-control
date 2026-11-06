// @vitest-environment happy-dom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { readLosslessBranch, switchLosslessBranch } from "./losslessBranch";
import { recordUiEvent } from "../system/uiEvents";

vi.mock("../system/uiEvents", () => ({ recordUiEvent: vi.fn() }));

type Details = { strSelectedBeta?: string; vecBetas?: { strName: string }[]; eAppUpdateError?: number };
let emit: (details: Details) => void;
const unregister = vi.fn();
const join = vi.fn();
const available = { strSelectedBeta: "public", vecBetas: [{ strName: "lsfg-vk" }] };
const register = vi.fn((_appid: number, cb: typeof emit) => { emit = cb; return { unregister }; });
const host = window as unknown as { SteamClient?: unknown };

beforeEach(() => {
  vi.useFakeTimers();
  vi.mocked(recordUiEvent).mockClear();
  unregister.mockReset();
  join.mockReset();
  register.mockClear();
  host.SteamClient = { Apps: { RegisterForAppDetails: register, JoinAppContentBeta: join } };
});
afterEach(() => { delete host.SteamClient; vi.useRealTimers(); });

it("reports missing APIs explicitly without attempting a change", async () => {
  delete host.SteamClient;
  await expect(readLosslessBranch()).resolves.toEqual({ selected: null, available: false, supported: false });
  await expect(switchLosslessBranch()).rejects.toThrow("lsfg_branch_unsupported");
  expect(join).not.toHaveBeenCalled();
});

it("reads the actual selected branch and cleans up a synchronous callback", async () => {
  register.mockImplementationOnce((_id, cb) => { cb(available); return { unregister }; });
  await expect(readLosslessBranch()).resolves.toEqual({ selected: "public", available: true, supported: true });
  expect(unregister).toHaveBeenCalledTimes(1);
  expect(vi.getTimerCount()).toBe(0);
  expect(join).not.toHaveBeenCalled();
});

it("waits for branch readback and requests the exact application only once", async () => {
  const promise = switchLosslessBranch();
  const finished = vi.fn();
  void promise.then(finished);
  emit(available);
  emit(available);
  await Promise.resolve();
  expect(join).toHaveBeenCalledExactlyOnceWith(993090, "lsfg-vk");
  expect(finished).not.toHaveBeenCalled();
  emit({ ...available, strSelectedBeta: "lsfg-vk" });
  await expect(promise).resolves.toMatchObject({ selected: "lsfg-vk" });
  expect(unregister).toHaveBeenCalledTimes(1);
  expect(vi.getTimerCount()).toBe(0);
});

it("does not write when the desired branch is already selected", async () => {
  const promise = switchLosslessBranch();
  emit({ ...available, strSelectedBeta: "lsfg-vk" });
  await promise;
  expect(join).not.toHaveBeenCalled();
});

it("refuses an unavailable branch", async () => {
  const promise = switchLosslessBranch();
  const assertion = expect(promise).rejects.toThrow("lsfg_branch_unavailable");
  emit({ strSelectedBeta: "public", vecBetas: [] });
  await assertion;
  expect(join).not.toHaveBeenCalled();
  expect(unregister).toHaveBeenCalledTimes(1);
});

it("times out instead of claiming success from a successful request", async () => {
  const promise = switchLosslessBranch(100);
  const assertion = expect(promise).rejects.toThrow("lsfg_branch_timeout");
  emit(available);
  await vi.advanceTimersByTimeAsync(100);
  await assertion;
  expect(unregister).toHaveBeenCalledTimes(1);
  emit({ ...available, strSelectedBeta: "lsfg-vk" });
  expect(join).toHaveBeenCalledTimes(1);
});

it("keeps a missing read unknown", async () => {
  const promise = readLosslessBranch(100);
  emit({ vecBetas: [] });
  await vi.advanceTimersByTimeAsync(100);
  await expect(promise).resolves.toEqual({ selected: null, available: false, supported: true });
  expect(unregister).toHaveBeenCalledTimes(1);
});

it.each(["throw", "reject", "update"])("handles a %s failure and releases the subscription", async (failure) => {
  if (failure === "throw") join.mockImplementationOnce(() => { throw new Error("failure"); });
  if (failure === "reject") join.mockRejectedValueOnce(new Error("failure"));
  const promise = switchLosslessBranch();
  const assertion = expect(promise).rejects.toThrow(failure === "update" ? "lsfg_branch_update_failed" : "lsfg_branch_failed");
  emit(available);
  if (failure === "update") emit({ ...available, eAppUpdateError: 7 });
  await assertion;
  expect(unregister).toHaveBeenCalledTimes(1);
  expect(vi.getTimerCount()).toBe(0);
});

it("cancels pending work when its consumer unmounts", async () => {
  const controller = new AbortController();
  const promise = switchLosslessBranch(100, controller.signal);
  const assertion = expect(promise).rejects.toThrow("lsfg_branch_cancelled");
  controller.abort();
  await assertion;
  emit(available);
  expect(join).not.toHaveBeenCalled();
  expect(unregister).toHaveBeenCalledTimes(1);
  expect(vi.getTimerCount()).toBe(0);
});

it("traces requested and confirmed selection without claiming a download", async () => {
  const promise = switchLosslessBranch();
  emit(available);
  expect(recordUiEvent).toHaveBeenCalledExactlyOnceWith("upscalers", "lsfg_branch_requested", { appid: 993090, branch: "lsfg-vk" });
  emit({ ...available, strSelectedBeta: "lsfg-vk" });
  await promise;
  expect(recordUiEvent).toHaveBeenLastCalledWith("upscalers", "lsfg_branch_confirmed", { appid: 993090, branch: "lsfg-vk", requested: true });
});

it("records a bounded failure code without exception details", async () => {
  join.mockImplementationOnce(() => { throw new Error("private detail"); });
  const promise = switchLosslessBranch();
  const assertion = expect(promise).rejects.toThrow("lsfg_branch_failed");
  emit(available);
  await assertion;
  expect(recordUiEvent).toHaveBeenLastCalledWith("upscalers", "lsfg_branch_failed", { appid: 993090, branch: "lsfg-vk", error: "lsfg_branch_failed" }, false);
});
