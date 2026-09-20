// @vitest-environment happy-dom
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CleanerEntry, CleanerPlan, CleanerResult, CleanerState } from "./types";

const api = vi.hoisted(() => ({ state: vi.fn(), scan: vi.fn(), prepare: vi.fn(), execute: vi.fn(), cancel: vi.fn() }));
vi.mock("../api", () => ({ getSteamCleanerState: api.state, scanSteamCleaner: api.scan, prepareSteamCleaner: api.prepare, executeSteamCleaner: api.execute, cancelSteamCleaner: api.cancel }));
import { useSteamCleaner } from "./useSteamCleaner";

const entry: CleanerEntry = { id: "entry", game_id: "game", appid: "10", name: "Game", kind: "compatdata", library_id: "lib", library_label: "Library", bytes: 500, installation: "installed", blocked_reason: null, requires_manual_selection: false, warnings: [] };
const state = (overrides: Partial<CleanerState> = {}): CleanerState => ({ schema_version: 1, available: true, status: "ready", scan_id: "scan", coverage_complete: true, entries: [entry], libraries: [], totals: { shadercache: 0, compatdata: 500, unknown: 0 }, progress: { processed: 0, total: null }, error: null, last_result: null, ...overrides });
const plan: CleanerPlan = { id: "plan", scan_id: "scan", entries: [entry], estimated_bytes: 500, requires_prefix_confirmation: true, expires_at: 9999999999 };
const outcome: CleanerResult = { operation_id: "operation", cancelled: false, estimated_bytes_removed: 500, items: [{ id: "entry", status: "deleted", bytes_removed: 500, reason: null }] };
const deferred = <T,>() => { let resolve!: (value: T) => void; const promise = new Promise<T>((done) => { resolve = done; }); return { promise, resolve }; };

beforeEach(() => {
  vi.resetAllMocks();
  api.state.mockResolvedValue(state());
  api.scan.mockResolvedValue(state({ scan_id: "new-scan" }));
  api.prepare.mockResolvedValue(plan);
  api.execute.mockResolvedValue(outcome);
  api.cancel.mockResolvedValue(state({ status: "cancelled" }));
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe("Steam Cleaner controller", () => {
  it("restores the current state without starting an automatic scan", async () => {
    const { result } = renderHook(useSteamCleaner);
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.state?.scan_id).toBe("scan");
    expect(api.scan).not.toHaveBeenCalled();
    await act(() => result.current.scan());
    expect(result.current.state?.scan_id).toBe("new-scan");
  });

  it("cancels a manually started analysis when Limpieza closes", async () => {
    const scanning = deferred<CleanerState>();
    api.scan.mockReturnValue(scanning.promise);
    const { result, unmount } = renderHook(useSteamCleaner);
    await waitFor(() => expect(result.current.loading).toBe(false));
    act(() => { void result.current.scan(); });
    await waitFor(() => expect(result.current.busy).toBe(true));
    unmount();
    expect(api.cancel).toHaveBeenCalledOnce();
    scanning.resolve(state({ scan_id: "fresh" }));
  });

  it("keeps a dismissed result hidden through refresh and scan, then shows a new cleanup", async () => {
    api.state.mockResolvedValue(state({ last_result: outcome }));
    api.scan.mockResolvedValue(state({ last_result: outcome }));
    const { result } = renderHook(useSteamCleaner);
    await waitFor(() => expect(result.current.result).toEqual(outcome));
    act(() => result.current.dismissResult());
    await act(() => result.current.refresh());
    await act(() => result.current.scan());
    expect(result.current.result).toBeNull();
    const next = { ...outcome, operation_id: "next-operation" };
    api.execute.mockResolvedValue(next);
    await act(() => result.current.prepare(["entry"]));
    await act(() => result.current.execute(true));
    expect(result.current.result).toEqual(next);
  });

  it("clears the previous result as soon as a new selection is prepared", async () => {
    api.state.mockResolvedValue(state({ last_result: outcome }));
    const { result } = renderHook(useSteamCleaner);
    await waitFor(() => expect(result.current.result).toEqual(outcome));
    await act(() => result.current.prepare(["entry"]));
    expect(result.current.result).toBeNull();
    expect(result.current.plan).not.toBeNull();
    await act(() => result.current.refresh());
    expect(result.current.result).toBeNull();
  });

  it("requires independent prefix confirmation and prevents double execution", async () => {
    const { result } = renderHook(useSteamCleaner);
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(() => result.current.prepare(["entry"]));
    expect(api.prepare).toHaveBeenCalledWith("scan", ["entry"]);
    await act(() => result.current.execute(false));
    expect(api.execute).not.toHaveBeenCalled();
    await act(async () => { await Promise.all([result.current.execute(true), result.current.execute(true)]); });
    expect(api.execute).toHaveBeenCalledExactlyOnceWith("plan", true);
    expect(result.current.result).toEqual(outcome);
    expect(result.current.plan).toBeNull();
  });

  it("cleans caches directly from the selection and rejects duplicate clicks", async () => {
    api.prepare.mockResolvedValue({ ...plan, requires_prefix_confirmation: false, entries: [{ ...entry, kind: "shadercache" }] });
    const { result } = renderHook(useSteamCleaner);
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => { await Promise.all([result.current.prepare(["entry"]), result.current.prepare(["entry"])]); });
    expect(api.prepare).toHaveBeenCalledExactlyOnceWith("scan", ["entry"]);
    expect(api.execute).toHaveBeenCalledExactlyOnceWith("plan", false);
    expect(result.current.plan).toBeNull();
    expect(result.current.result).toEqual(outcome);
    expect(result.current.busy).toBe(false);
  });

  it("does not begin a direct cleanup if the section closes during preparation", async () => {
    const preparation = deferred<CleanerPlan>();
    api.prepare.mockReturnValue(preparation.promise);
    const { result, unmount } = renderHook(useSteamCleaner);
    await waitFor(() => expect(result.current.loading).toBe(false));
    let running!: Promise<void>;
    act(() => { running = result.current.prepare(["entry"]); });
    unmount();
    await act(async () => { preparation.resolve({ ...plan, requires_prefix_confirmation: false }); await running; });
    expect(api.execute).not.toHaveBeenCalled();
  });

  it("preserves per-entry partial failures without reporting all data as deleted", async () => {
    const partial: CleanerResult = { ...outcome, estimated_bytes_removed: 0, items: [{ id: "entry", status: "error", bytes_removed: 0, reason: "io_error" }] };
    api.execute.mockResolvedValue(partial);
    const { result } = renderHook(useSteamCleaner);
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(() => result.current.prepare(["entry"]));
    await act(() => result.current.execute(true));
    expect(result.current.result).toEqual(partial);
  });

  it("keeps the inventory and exposes only a normalized code on RPC failure", async () => {
    api.scan.mockRejectedValue(new Error("RuntimeError: unsafe_path /home/private-user/data"));
    const { result } = renderHook(useSteamCleaner);
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(() => result.current.scan());
    expect(result.current.error).toBe("unsafe_path");
    expect(result.current.state?.entries).toEqual([entry]);
    expect(api.execute).not.toHaveBeenCalled();
  });

  it("does not let an old progress read overwrite execution readback", async () => {
    const { result } = renderHook(useSteamCleaner);
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(() => result.current.prepare(["entry"]));
    vi.useFakeTimers();
    const execution = deferred<CleanerResult>();
    const progress = deferred<CleanerState>();
    api.execute.mockReturnValue(execution.promise);
    api.state.mockReturnValueOnce(progress.promise).mockResolvedValue(state({ status: "ready", scan_id: null, entries: [], last_result: outcome }));
    let running!: Promise<void>;
    act(() => { running = result.current.execute(true); });
    await act(() => vi.advanceTimersByTimeAsync(800));
    await act(async () => { execution.resolve(outcome); await running; });
    await act(async () => { progress.resolve(state({ status: "cleaning" })); });
    expect(result.current.state?.status).toBe("ready");
    expect(result.current.state?.entries).toEqual([]);
    expect(result.current.busy).toBe(false);
  });

  it("does not restore an earlier cleanup result when a new execution fails", async () => {
    api.state.mockResolvedValue(state({ last_result: outcome }));
    const { result } = renderHook(useSteamCleaner);
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(() => result.current.prepare(["entry"]));
    vi.useFakeTimers();
    api.execute.mockImplementation(async () => {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      throw new Error("internal_error");
    });
    let running!: Promise<void>;
    act(() => { running = result.current.execute(true); });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); await running; });
    expect(result.current.error).toBe("internal_error");
    expect(result.current.result).toBeNull();
  });

  it("cancels while an execution is pending and stops polling after unmount", async () => {
    const { result, unmount } = renderHook(useSteamCleaner);
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(() => result.current.prepare(["entry"]));
    vi.useFakeTimers();
    const execution = deferred<CleanerResult>();
    api.execute.mockReturnValue(execution.promise);
    let running!: Promise<void>;
    act(() => { running = result.current.execute(true); });
    await act(() => result.current.cancel());
    expect(api.cancel).toHaveBeenCalledOnce();
    unmount();
    const reads = api.state.mock.calls.length;
    await act(async () => { execution.resolve({ ...outcome, cancelled: true }); await running; await vi.advanceTimersByTimeAsync(2400); });
    expect(api.state).toHaveBeenCalledTimes(reads);
  });
});
