// @vitest-environment happy-dom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
vi.mock("../api", () => ({ getUpscalerLive: vi.fn(), getLsfgStatus: vi.fn(), getMakoRuntime: vi.fn() }));
import { getLsfgStatus, getMakoRuntime, getUpscalerLive } from "../api";
import { useOverlayLive } from "./useOverlayLive";
const read = vi.mocked(getUpscalerLive);
const active = { result: "active", resolution: { render: [753, 471], output: [1280, 800] } };
beforeEach(() => {
  vi.useFakeTimers();
  read.mockResolvedValue(active);
  vi.mocked(getMakoRuntime).mockResolvedValue({ observed: false });
  vi.mocked(getLsfgStatus).mockResolvedValue({ profiles: {} } as never);
});
afterEach(() => { cleanup(); vi.resetAllMocks(); vi.useRealTimers(); });
it("continues reading after activation and clears unavailable readings", async () => {
  const { result } = renderHook(() => useOverlayLive("1", true));
  await act(async () => {});
  expect(result.current.live?.resolution?.render[1]).toBe(471);
  read.mockResolvedValue({ ...active, resolution: { render: [1280, 800], output: [1280, 800] } });
  await act(async () => vi.advanceTimersByTimeAsync(1500));
  expect(result.current.live?.resolution?.render[1]).toBe(800);
  read.mockRejectedValue(new Error("offline"));
  await act(async () => vi.advanceTimersByTimeAsync(1500));
  expect(result.current.live).toBeNull();
});
it("never overlaps slow requests and ignores responses from a previous game", async () => {
  let resolve!: (value: typeof active) => void;
  read.mockReturnValueOnce(new Promise(done => { resolve = done; }));
  const { result, rerender } = renderHook(({ id }) => useOverlayLive(id, true), { initialProps: { id: "1" } });
  await act(async () => vi.advanceTimersByTimeAsync(6000));
  expect(read).toHaveBeenCalledTimes(1);
  rerender({ id: "2" });
  await act(async () => {});
  expect(read).toHaveBeenLastCalledWith("2");
  await act(async () => resolve({ result: "inactive", resolution: active.resolution }));
  expect(result.current.live?.result).toBe("active");
});
it("reads a Lossless profile without an OptiScaler installation and clears it after removal", async () => {
  const profile = { multiplier: 2, flow: "balanced", performance: true };
  vi.mocked(getLsfgStatus).mockResolvedValue({ profiles: { "1": profile } } as never);
  const { result } = renderHook(() => useOverlayLive("1", false));
  await act(async () => {});
  expect(read).not.toHaveBeenCalled();
  expect(result.current.lossless).toEqual(profile);
  vi.mocked(getLsfgStatus).mockResolvedValue({ profiles: {} } as never);
  await act(async () => vi.advanceTimersByTimeAsync(1500));
  expect(result.current.lossless).toBeNull();
});

it("expires previous evidence while a later read is stalled", async () => {
  const { result } = renderHook(() => useOverlayLive("1", true));
  await act(async () => {});
  expect(result.current.live?.result).toBe("active");
  read.mockReturnValueOnce(new Promise(() => {}));
  await act(async () => vi.advanceTimersByTimeAsync(6500));
  expect(result.current.live).toBeNull();
  expect(read).toHaveBeenCalledTimes(2);
});

const noHeadroom = { observed: true, scaling_active: false,
  requested: { scaling_enabled: true }, applied: { scaling_enabled: true },
  scaling_inactive_reason: "gamescope-presentation-target-no-headroom" as const };
it("warns without OptiScaler only for observed spatial scaling without headroom", async () => {
  vi.mocked(getMakoRuntime).mockResolvedValue(noHeadroom);
  const { result } = renderHook(() => useOverlayLive("1", false));
  await act(async () => {});
  expect(result.current.makoResolutionWarning).toBe(true);
  for (const state of [
    { ...noHeadroom, scaling_active: true },
    { ...noHeadroom, observed: false },
    { ...noHeadroom, requested: { scaling_enabled: false } },
    { ...noHeadroom, applied: { scaling_enabled: false } },
    { ...noHeadroom, scaling_inactive_reason: null },
    { ...noHeadroom, error: "mako_runtime_error" },
    { ...noHeadroom, pending: { process_restart: true } },
  ]) {
    vi.mocked(getMakoRuntime).mockResolvedValue(state);
    await act(async () => vi.advanceTimersByTimeAsync(1500));
    expect(result.current.makoResolutionWarning).toBe(false);
  }
});
it("clears the Mako warning on failure, stalled reads and game changes", async () => {
  const mako = vi.mocked(getMakoRuntime);
  mako.mockResolvedValue(noHeadroom);
  const { result, rerender } = renderHook(({ id }) => useOverlayLive(id, false), { initialProps: { id: "1" } });
  await act(async () => {});
  expect(result.current.makoResolutionWarning).toBe(true);
  mako.mockRejectedValueOnce(new Error("offline"));
  await act(async () => vi.advanceTimersByTimeAsync(1500));
  expect(result.current.makoResolutionWarning).toBe(false);
  await act(async () => vi.advanceTimersByTimeAsync(1500));
  expect(result.current.makoResolutionWarning).toBe(true);
  let resolve!: (value: typeof noHeadroom) => void;
  mako.mockReturnValueOnce(new Promise(done => { resolve = done; }));
  await act(async () => vi.advanceTimersByTimeAsync(6500));
  expect(result.current.makoResolutionWarning).toBe(false);
  mako.mockResolvedValue({ observed: false });
  rerender({ id: "2" });
  await act(async () => resolve(noHeadroom));
  expect(result.current.makoResolutionWarning).toBe(false);
});

it("keeps OptiScaler readings fresh while Mako is stalled", async () => {
  vi.mocked(getMakoRuntime).mockReturnValue(new Promise(() => {}));
  const { result } = renderHook(() => useOverlayLive("1", true));
  await act(async () => {});
  expect(result.current.live?.resolution?.render[1]).toBe(471);
  read.mockResolvedValue({ ...active, resolution: { render: [1280, 800], output: [1280, 800] } });
  await act(async () => vi.advanceTimersByTimeAsync(6500));
  expect(result.current.live?.resolution?.render[1]).toBe(800);
  expect(result.current.makoResolutionWarning).toBe(false);
  expect(getMakoRuntime).toHaveBeenCalledTimes(1);
});

const generating = { observed: true, active: true, role: "frame-generation",
  applied: { frame_generation_enabled: true, multiplier: 2 }, pending: {}, error: null };
it("reports Mako generation only with current confirmed applied FG evidence", async () => {
  const mako = vi.mocked(getMakoRuntime);
  mako.mockResolvedValue(generating);
  const { result } = renderHook(() => useOverlayLive("1", false));
  await act(async () => {});
  expect(result.current.makoMultiplier).toBe(2);
  const rejected: Awaited<ReturnType<typeof getMakoRuntime>>[] = [
    { ...generating, observed: false }, { ...generating, active: false },
    { ...generating, active: null }, { ...generating, role: "spatial-scaling" },
    { ...generating, applied: { frame_generation_enabled: false, multiplier: 2 } },
    { ...generating, applied: { frame_generation_enabled: true, multiplier: 1 } },
    { ...generating, applied: { frame_generation_enabled: true, multiplier: "2" } },
    { ...generating, applied: { frame_generation_enabled: true } },
    { ...generating, error: "mako_runtime_error" },
    ...["frame_generation_private", "spatial_private", "swapchain_recreation", "process_restart"].map(key =>
      ({ ...generating, pending: { [key]: true } })),
  ];
  for (const state of rejected) {
    mako.mockResolvedValue(state);
    await act(async () => vi.advanceTimersByTimeAsync(1500));
    expect(result.current.makoMultiplier).toBeNull();
  }
});
it("clears Mako FG on failure, stalled reads and game changes and ignores stale responses", async () => {
  const mako = vi.mocked(getMakoRuntime);
  mako.mockResolvedValue(generating);
  const { result, rerender } = renderHook(({ id }) => useOverlayLive(id, false), { initialProps: { id: "1" } });
  await act(async () => {});
  expect(result.current.makoMultiplier).toBe(2);
  mako.mockRejectedValueOnce(new Error("offline"));
  await act(async () => vi.advanceTimersByTimeAsync(1500));
  expect(result.current.makoMultiplier).toBeNull();
  await act(async () => vi.advanceTimersByTimeAsync(1500));
  expect(result.current.makoMultiplier).toBe(2);
  let resolve!: (value: typeof generating) => void;
  mako.mockReturnValueOnce(new Promise(done => { resolve = done; }));
  await act(async () => vi.advanceTimersByTimeAsync(6500));
  expect(result.current.makoMultiplier).toBeNull();
  mako.mockResolvedValue({ observed: false });
  rerender({ id: "2" });
  await act(async () => resolve(generating));
  expect(result.current.makoMultiplier).toBeNull();
});

it("discards expired Mako responses for the same game and recovers on a fresh read", async () => {
  const mako = vi.mocked(getMakoRuntime);
  mako.mockResolvedValue(generating);
  const { result } = renderHook(() => useOverlayLive("1", false));
  await act(async () => {});
  expect(result.current.makoMultiplier).toBe(2);
  let resolve!: (value: typeof generating) => void;
  mako.mockReturnValueOnce(new Promise(done => { resolve = done; }));
  await act(async () => vi.advanceTimersByTimeAsync(6500));
  expect(result.current.makoMultiplier).toBeNull();
  await act(async () => resolve(generating));
  expect(result.current.makoMultiplier).toBeNull();
  expect(mako).toHaveBeenCalledTimes(2);
  await act(async () => vi.advanceTimersByTimeAsync(1500));
  expect(mako).toHaveBeenCalledTimes(3);
  expect(result.current.makoMultiplier).toBe(2);
});

const spatialMako = { observed: true, active: false, role: "frame-generation", scaling_active: true,
  spatial_methods: { active_method: "mako" }, requested: { scaling_enabled: true },
  applied: { scaling_enabled: true, frame_generation_enabled: false },
  spatial_resolution: { render: [1280, 720] as [number, number], output: [1920, 1080] as [number, number] } };
it("observes spatial Mako independently of frame generation and rejects unavailable evidence", async () => {
  vi.mocked(getMakoRuntime).mockResolvedValue(spatialMako);
  const { result } = renderHook(() => useOverlayLive("1", false));
  await act(async () => {});
  expect(result.current.makoSpatial).toEqual(spatialMako.spatial_resolution);
  expect(result.current.makoMultiplier).toBeNull();
  for (const change of [{ observed: false }, { scaling_active: false }, { error: "failed" },
    { pending: { swapchain_recreation: true } }, { spatial_methods: { active_method: "ls1" } },
    { requested: { scaling_enabled: false } }, { applied: { scaling_enabled: false } },
    { spatial_resolution: null }, { spatial_resolution: { render: [0, 720], output: [1920, 1080] } }]) {
    vi.mocked(getMakoRuntime).mockResolvedValue({ ...spatialMako, ...change } as never);
    await act(async () => vi.advanceTimersByTimeAsync(1500));
    expect(result.current.makoSpatial).toBeNull();
  }
});
it("expires spatial evidence and ignores late readings and previous games", async () => {
  vi.mocked(getMakoRuntime).mockResolvedValue(spatialMako);
  const { result, rerender } = renderHook(({ id }) => useOverlayLive(id, false), { initialProps: { id: "1" } });
  await act(async () => {});
  let resolve!: (value: typeof spatialMako) => void;
  vi.mocked(getMakoRuntime).mockReturnValueOnce(new Promise(done => { resolve = done; }));
  await act(async () => vi.advanceTimersByTimeAsync(6500));
  expect(result.current.makoSpatial).toBeNull();
  await act(async () => resolve(spatialMako));
  expect(result.current.makoSpatial).toBeNull();
  await act(async () => vi.advanceTimersByTimeAsync(1500));
  expect(result.current.makoSpatial).not.toBeNull();
  vi.mocked(getMakoRuntime).mockRejectedValue(new Error("offline"));
  rerender({ id: "2" });
  await act(async () => {});
  expect(result.current.makoSpatial).toBeNull();
});
