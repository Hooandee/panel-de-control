// @vitest-environment happy-dom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({ Navigation: {} }));
vi.mock("../api", () => ({ getUpscalerLive: vi.fn(), pressUpscalerKey: vi.fn() }));
vi.mock("../i18n", () => ({ useI18n: vi.fn() }));
vi.mock("./parts", () => ({ Label: vi.fn(), ListCard: vi.fn(), ListRow: vi.fn(), Note: vi.fn() }));
vi.mock("./pageMemory", () => ({ holdPage: vi.fn() }));

import { getUpscalerLive } from "../api";
import { useUpscalerLive } from "./LivePanel";

const active = { result: "active", fps: 40, resolution: { render: [960, 600], output: [1280, 800] }, fg: true };
const read = vi.mocked(getUpscalerLive);

beforeEach(() => {
  vi.useFakeTimers();
  read.mockReset();
  read.mockResolvedValue(active as Awaited<ReturnType<typeof getUpscalerLive>>);
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

it("clears readings between sessions even when the next session cannot be read", async () => {
  const { result, rerender } = renderHook(({ enabled }) => useUpscalerLive("1", enabled), { initialProps: { enabled: true } });
  await act(async () => {});
  expect(result.current[0].fps).toBe(40);
  rerender({ enabled: false });
  expect(result.current[0]).toMatchObject({ fps: null, render: null, output: null, generating: null });
  read.mockRejectedValue(new Error("unavailable"));
  rerender({ enabled: true });
  await act(async () => {});
  expect(result.current[0]).toMatchObject({ fps: null, render: null, output: null });
});

it("checks a pending installation once again after a new session", async () => {
  const onActive = vi.fn();
  const { rerender } = renderHook(({ enabled }) => useUpscalerLive("1", enabled, onActive), { initialProps: { enabled: true } });
  await act(async () => {});
  await act(async () => vi.advanceTimersByTimeAsync(1500));
  expect(onActive).toHaveBeenCalledTimes(1);
  rerender({ enabled: false });
  rerender({ enabled: true });
  await act(async () => {});
  expect(onActive).toHaveBeenCalledTimes(2);
});

it("rearms verification when an installation becomes pending again", async () => {
  const onActive = vi.fn();
  const { rerender } = renderHook(({ pending }) => useUpscalerLive("1", true, pending ? onActive : undefined), { initialProps: { pending: true } });
  await act(async () => {});
  expect(onActive).toHaveBeenCalledTimes(1);
  rerender({ pending: false });
  rerender({ pending: true });
  await act(async () => vi.advanceTimersByTimeAsync(1500));
  expect(onActive).toHaveBeenCalledTimes(2);
});
