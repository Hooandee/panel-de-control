// @vitest-environment happy-dom
import { act, renderHook } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const runtime = vi.hoisted(() => ({
  discover: vi.fn(),
  resolve: vi.fn(),
  syncProfile: vi.fn(),
  subscribe: vi.fn(),
}));

vi.mock("./performanceRuntime", () => ({
  discoverSteamPerformanceComponents: runtime.discover,
  resolveSteamPerformanceStore: runtime.resolve,
  syncSteamPerformanceProfile: runtime.syncProfile,
  subscribeSteamPerformanceState: runtime.subscribe,
}));

import { useSteamPerformanceSurface } from "./useSteamPerformanceSurface";
import {
  resetSteamPerformanceDiagnostics,
  steamPerformanceDiagnostics,
} from "./performanceDiagnostics";

const Native = () => null;

describe("useSteamPerformanceSurface", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    resetSteamPerformanceDiagnostics();
    runtime.discover.mockReset();
    runtime.resolve.mockReset();
    runtime.syncProfile.mockReset();
    runtime.subscribe.mockReset();
    runtime.subscribe.mockReturnValue(vi.fn());
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("publishes the one Steam route selected by the hydrated store", () => {
    runtime.discover.mockReturnValue({
      profile: Native,
      legacyFrameRate: Native,
      appFrameRate: Native,
      disableFrameLimit: Native,
      reset: Native,
    });
    runtime.resolve.mockReturnValue({
      msgLimits: {
        disable_refresh_rate_management: true,
        is_split_scaling_and_filtering_supported: false,
      },
    });

    const { result } = renderHook(() => useSteamPerformanceSurface());

    expect(result.current.status).toBe("ready");
    expect(result.current.rows.map((row) => row.id)).toEqual([
      "appFrameRate",
      "disableFrameLimit",
      "reset",
    ]);
    expect(steamPerformanceDiagnostics()?.current.surface).toMatchObject({
      status: "ready",
      frame_rate_path: "app_target",
      split_scaling: false,
      row_ids: ["appFrameRate", "disableFrameLimit", "reset"],
    });
  });

  it("keeps Steam on the profile selected by the shared power scope", () => {
    runtime.discover.mockReturnValue({ legacyFrameRate: Native });
    runtime.resolve.mockReturnValue({ msgLimits: {} });

    renderHook(() => useSteamPerformanceSurface("game", 42));

    expect(runtime.syncProfile).toHaveBeenCalledWith("game", 42, true);
  });

  it("reports loading before the first effect without touching Steam during render", () => {
    runtime.discover.mockReturnValue({ legacyFrameRate: Native, reset: Native });
    runtime.resolve.mockReturnValue({ msgLimits: {} });
    const Probe = () => <span>{useSteamPerformanceSurface().status}</span>;

    expect(renderToString(<Probe />)).toContain("loading");
    expect(runtime.discover).not.toHaveBeenCalled();
    expect(runtime.resolve).not.toHaveBeenCalled();
  });

  it("converges when Steam loads the performance module after the block mounts", () => {
    runtime.discover
      .mockReturnValueOnce({})
      .mockReturnValue({ legacyFrameRate: Native, reset: Native });
    runtime.resolve
      .mockReturnValueOnce(null)
      .mockReturnValue({ msgLimits: {} });

    const { result } = renderHook(() => useSteamPerformanceSurface());
    expect(result.current.status).toBe("unavailable");

    act(() => { vi.advanceTimersByTime(2000); });

    expect(result.current.status).toBe("ready");
    expect(result.current.rows.map((row) => row.id)).toEqual([
      "legacyFrameRate",
      "reset",
    ]);
  });

  it("releases Steam's registration and retry timer on unmount", () => {
    const unsubscribe = vi.fn();
    runtime.discover.mockReturnValue({});
    runtime.resolve.mockReturnValue(null);
    runtime.subscribe.mockReturnValue(unsubscribe);

    const { unmount } = renderHook(() => useSteamPerformanceSurface());
    unmount();
    vi.advanceTimersByTime(4000);

    expect(unsubscribe).toHaveBeenCalledOnce();
    expect(runtime.discover).toHaveBeenCalledOnce();
  });

  it("does not claim availability when only reset chrome resolved", () => {
    runtime.discover.mockReturnValue({ reset: Native });
    runtime.resolve.mockReturnValue({ msgLimits: {} });

    const { result } = renderHook(() => useSteamPerformanceSurface());

    expect(result.current).toEqual({ status: "unavailable", rows: [] });
  });

  it("retries discovery after resolving only reset chrome", () => {
    runtime.discover
      .mockReturnValueOnce({ reset: Native })
      .mockReturnValue({ legacyFrameRate: Native, reset: Native });
    runtime.resolve.mockReturnValue({ msgLimits: {} });

    const { result } = renderHook(() => useSteamPerformanceSurface());
    expect(result.current.status).toBe("unavailable");

    act(() => { vi.advanceTimersByTime(2000); });

    expect(result.current.status).toBe("ready");
    expect(result.current.rows.map((row) => row.id)).toEqual([
      "legacyFrameRate",
      "reset",
    ]);
  });

  it("replaces a non-empty snapshot when the live CEF component appears", () => {
    const Snapshot = () => null;
    const Current = () => null;
    runtime.discover
      .mockReturnValueOnce({ legacyFrameRate: Snapshot, reset: Native })
      .mockReturnValue({ legacyFrameRate: Current, reset: Native });
    runtime.resolve.mockReturnValue({ msgLimits: {} });

    const { result } = renderHook(() => useSteamPerformanceSurface());
    expect(result.current.rows[0]?.Component).toBe(Snapshot);

    act(() => { vi.advanceTimersByTime(2000); });

    expect(result.current.rows[0]?.Component).toBe(Current);
  });
});
