// @vitest-environment happy-dom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
vi.mock("../api", () => ({ getUpscalerLive: vi.fn(), getLsfgStatus: vi.fn() }));
import { getLsfgStatus, getUpscalerLive } from "../api";
import { useOverlayLive } from "./useOverlayLive";
const read = vi.mocked(getUpscalerLive);
const active = { result: "active", resolution: { render: [753, 471], output: [1280, 800] } };
beforeEach(() => {
  vi.useFakeTimers();
  read.mockResolvedValue(active);
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
