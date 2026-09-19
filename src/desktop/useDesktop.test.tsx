// @vitest-environment happy-dom
import { act, cleanup, render, renderHook, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DesktopState } from "../api";

const api = vi.hoisted(() => ({
  getDesktopState: vi.fn(),
  retryDesktopMigration: vi.fn(),
  setDesktopModeEnabled: vi.fn(),
  setDesktopPowerLimits: vi.fn(),
  setDesktopPowerMode: vi.fn(),
}));

vi.mock("../api", () => api);

let desktop: typeof import("./useDesktop");

const initialState: DesktopState = {
  enabled: true,
  automatic: false,
  manual_enabled: true,
  migration_pending: false,
  migration_failure: null,
  power: {
    supported: true, cpu_supported: true, cpu_policy_supported: false,
    cpu_policy: null, gpu_supported: true, mode: "balanced", cpu_w: 20, gpu_w: 30,
    cpu_min_w: 5, cpu_max_w: 60, gpu_min_w: 5, gpu_max_w: 100, presets: {},
  },
  telemetry: null,
  cpu: null,
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

describe("shared desktop state", () => {
  beforeEach(async () => {
    vi.resetModules();
    vi.resetAllMocks();
    desktop = await import("./useDesktop");
    api.getDesktopState.mockResolvedValue(initialState);
  });
  afterEach(cleanup);

  it("shares the startup read between the QAM catalog and mounted views", async () => {
    desktop.ensureDesktopState();
    await waitFor(() => expect(desktop.getDesktopSnapshot()?.enabled).toBe(true));
    const Probe = () => <div>{desktop.useDesktopState().state?.enabled ? "enabled" : "loading"}</div>;
    render(<><Probe /><Probe /></>);

    await waitFor(() => expect(screen.getAllByText("enabled")).toHaveLength(2));
    await new Promise((resolve) => window.setTimeout(resolve, 0));
    expect(api.getDesktopState).toHaveBeenCalledOnce();
  });

  it.each([
    ["applyMode", "before"], ["applyMode", "after"],
    ["applyLimits", "before"], ["applyLimits", "after"],
  ] as const)("%s reads fresh state when an older read finishes %s the readback", async (action, order) => {
    const { result } = renderHook(() => desktop.useDesktopState());
    await waitFor(() => expect(result.current.state).toEqual(initialState));
    const previousRead = deferred<DesktopState>();
    const freshRead = deferred<DesktopState>();
    api.getDesktopState.mockReturnValueOnce(previousRead.promise).mockReturnValueOnce(freshRead.promise);
    api.setDesktopPowerMode.mockResolvedValue({ ok: true });
    api.setDesktopPowerLimits.mockResolvedValue({ ok: true });

    act(() => {
      result.current.refresh();
      result.current.refresh();
    });
    expect(api.getDesktopState).toHaveBeenCalledTimes(2);
    await act(async () => {
      if (action === "applyMode") result.current.applyMode("performance");
      else result.current.applyLimits(30, 40);
    });
    if (order === "before") await act(async () => previousRead.resolve(initialState));
    expect(api.getDesktopState).toHaveBeenCalledTimes(3);
    act(() => result.current.refresh());
    expect(api.getDesktopState).toHaveBeenCalledTimes(3);
    const updated: DesktopState = {
      ...initialState,
      power: { ...initialState.power, mode: "performance", cpu_w: 30, gpu_w: 40 },
    };
    await act(async () => freshRead.resolve(updated));
    if (order === "after") await act(async () => previousRead.resolve(initialState));
    expect(result.current.state).toEqual(updated);
    expect(desktop.getDesktopSnapshot()).toEqual(updated);
  });

  it.each([
    ["setEnabled", "resolve"], ["setEnabled", "reject"],
    ["retryMigration", "resolve"], ["retryMigration", "reject"],
  ] as const)("%s keeps its authoritative response when an older read ends with %s", async (action, outcome) => {
    const { result } = renderHook(() => desktop.useDesktopState());
    await waitFor(() => expect(result.current.state).toEqual(initialState));
    const previousRead = deferred<DesktopState>();
    api.getDesktopState.mockReturnValueOnce(previousRead.promise);
    const updated = { ...initialState, enabled: false, manual_enabled: false };
    api.setDesktopModeEnabled.mockResolvedValue(updated);
    api.retryDesktopMigration.mockResolvedValue(updated);
    act(() => result.current.refresh());
    await act(async () => {
      if (action === "setEnabled") result.current.setEnabled(false);
      else result.current.retryMigration();
    });
    expect(result.current.state).toEqual(updated);
    await act(async () => {
      if (outcome === "resolve") previousRead.resolve(initialState);
      else previousRead.reject(new Error("obsolete read failed"));
    });
    expect(result.current.state).toEqual(updated);
    expect(result.current.error).toBe(false);
  });

  it("reports a failed fresh read and recovers on the next refresh", async () => {
    const { result } = renderHook(() => desktop.useDesktopState());
    await waitFor(() => expect(result.current.state).toEqual(initialState));
    api.setDesktopPowerLimits.mockResolvedValue({ ok: true });
    api.getDesktopState.mockRejectedValueOnce(new Error("readback failed"));
    await act(async () => result.current.applyLimits(30, 40));
    expect(result.current.error).toBe(true);
    expect(result.current.state).toEqual(initialState);
    const updated = { ...initialState, power: { ...initialState.power, cpu_w: 30, gpu_w: 40 } };
    api.getDesktopState.mockResolvedValueOnce(updated);
    await act(async () => result.current.refresh());
    expect(result.current.state).toEqual(updated);
    expect(result.current.error).toBe(false);
  });
});
