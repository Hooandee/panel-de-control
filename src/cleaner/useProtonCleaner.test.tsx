// @vitest-environment happy-dom
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ProtonPlan, ProtonResult, ProtonState } from "./protonTypes";

const api = vi.hoisted(() => ({ state: vi.fn(), scan: vi.fn(), prepare: vi.fn(), execute: vi.fn(), cancel: vi.fn() }));
vi.mock("../api", () => ({
  getProtonCleanerState: api.state,
  scanProtonCleaner: api.scan,
  prepareProtonCleaner: api.prepare,
  executeProtonCleaner: api.execute,
  cancelSteamCleaner: api.cancel,
}));
import { useProtonCleaner } from "./useProtonCleaner";

const entry = { id: "tool", name: "GE-Proton-Old", tool_name: "ge-proton-old", source: "custom" as const, appid: null, bytes: 100, status: "unused" as const, selectable: true, recommended: true, reason: null };
const state = (overrides: Partial<ProtonState> = {}): ProtonState => ({ schema_version: 1, available: true, status: "ready", scan_id: "scan", coverage_complete: true, entries: [entry], totals: { bytes: 100, unknown: 0 }, progress: { processed: 1, total: 1 }, error: null, last_result: null, ...overrides });
const plan: ProtonPlan = { id: "plan", scan_id: "scan", entries: [entry], estimated_bytes: 100, expires_at: 9999999999 };
const outcome: ProtonResult = { operation_id: "operation", items: [{ id: "tool", status: "deleted", reason: null, bytes_removed: 100 }], estimated_bytes_removed: 100, cancelled: false };
const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
};

beforeEach(() => {
  vi.resetAllMocks();
  api.state.mockResolvedValue(state());
  api.scan.mockResolvedValue(state({ scan_id: "fresh" }));
  api.prepare.mockResolvedValue(plan);
  api.execute.mockResolvedValue(outcome);
  api.cancel.mockResolvedValue(state({ status: "cancelled" }));
});
afterEach(cleanup);

describe("Proton cleaner controller", () => {
  it("waits for the hub to start its scan", async () => {
    const { result } = renderHook(useProtonCleaner);
    await waitFor(() => expect(result.current.state?.scan_id).toBe("scan"));
    expect(result.current.loading).toBe(true);
    expect(result.current.busy).toBe(true);
    expect(api.scan).not.toHaveBeenCalled();
    await act(() => result.current.scan());
    expect(result.current.state?.scan_id).toBe("fresh");
    expect(result.current.loading).toBe(false);
  });

  it("prepares and deletes only the explicit tool ids", async () => {
    const { result } = renderHook(useProtonCleaner);
    await waitFor(() => expect(result.current.state?.scan_id).toBe("scan"));
    await act(() => result.current.scan());
    await act(() => result.current.clean(["tool"]));
    expect(api.prepare).toHaveBeenCalledWith("fresh", ["tool"]);
    expect(api.execute).toHaveBeenCalledWith("plan");
    expect(result.current.result).toEqual(outcome);
  });

  it("cancels a pending scan when Limpieza closes", async () => {
    api.scan.mockReturnValue(new Promise(() => undefined));
    const { result, unmount } = renderHook(useProtonCleaner);
    await waitFor(() => expect(result.current.state?.scan_id).toBe("scan"));
    act(() => { void result.current.scan(); });
    await waitFor(() => expect(result.current.busy).toBe(true));
    unmount();
    expect(api.cancel).toHaveBeenCalledOnce();
  });

  it("shows Proton as queued before the disk scan starts", async () => {
    const { result } = renderHook(useProtonCleaner);
    await waitFor(() => expect(result.current.state?.scan_id).toBe("scan"));
    await act(() => result.current.scan());
    expect(result.current.loading).toBe(false);

    act(() => result.current.queueScan());

    expect(result.current.loading).toBe(true);
    expect(result.current.busy).toBe(true);
    expect(api.scan).toHaveBeenCalledOnce();
  });

  it("keeps Proton queued when the initial cached state arrives late", async () => {
    const cached = deferred<ProtonState>();
    api.state.mockReturnValue(cached.promise);
    const { result } = renderHook(useProtonCleaner);

    act(() => result.current.queueScan());
    await act(async () => { cached.resolve(state()); });

    expect(result.current.state?.scan_id).toBe("scan");
    expect(result.current.loading).toBe(true);
    expect(result.current.busy).toBe(true);
    expect(api.scan).not.toHaveBeenCalled();
  });
});
