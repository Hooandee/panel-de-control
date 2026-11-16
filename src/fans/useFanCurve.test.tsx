// @vitest-environment happy-dom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FanCurveState } from "../api";
import report from "../../tests/data/fan_custom_restore.json";

const mocks = vi.hoisted(() => ({
  getFanCurveState: vi.fn(),
  setFanCurvePoints: vi.fn(),
}));
vi.mock("../api", () => ({
  ...mocks,
  setFanFollowGlobal: vi.fn(),
  setFanPreset: vi.fn(),
  setFanCurveAuto: vi.fn(),
  setFanSplit: vi.fn(),
  setFanAdaptive: vi.fn(),
  setFanAdaptiveBias: vi.fn(),
  setFanExperimental: vi.fn(),
  resetFanControl: vi.fn(),
}));
vi.mock("../tdp/useRunningGame", () => ({ useRunningGame: () => null }));

import { useFanCurve } from "./useFanCurve";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("returning to the custom fan curve", () => {
  it.each([true, false])("restores saved points when available: %s", async (hasSavedCurve) => {
    const state = {
      preset: report.preset,
      points: report.preset_points,
      custom_points: hasSavedCurve ? report.custom_points : null,
      follows_global: true,
      presets: [],
    } as unknown as FanCurveState;
    mocks.getFanCurveState.mockResolvedValue(state);
    mocks.setFanCurvePoints.mockImplementation(async (points) => ({ ...state, preset: "custom", points }));
    const { result } = renderHook(() => useFanCurve());
    await act(async () => { await Promise.resolve(); });
    await act(async () => { result.current.onCustomMode(); });
    const expected = hasSavedCurve ? report.custom_points : report.preset_points;
    expect(mocks.setFanCurvePoints).toHaveBeenCalledWith(expected, "global", null);
    expect(result.current.state?.points).toEqual(expected);
  });
});

describe("per-channel curves (Por separado)", () => {
  const A: [number, number][] = [[40, 100], [95, 255]];
  const B: [number, number][] = [[40, 0], [95, 255]];
  const split = {
    preset: "custom", points: A, follows_global: true, presets: [], split_available: true, split: true,
    channels: [{ key: "cpu", preset: "custom", points: A }, { key: "gpu", preset: "custom", points: A }],
  } as unknown as FanCurveState;

  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it("debounces each fan on its own and sends the channel", async () => {
    mocks.getFanCurveState.mockResolvedValue(split);
    mocks.setFanCurvePoints.mockImplementation(async () => split);
    const { result } = renderHook(() => useFanCurve());
    await act(async () => { await Promise.resolve(); });
    act(() => {
      result.current.onChannelCurve("cpu", A);
      result.current.onChannelCurve("gpu", B);
    });
    expect(mocks.setFanCurvePoints).not.toHaveBeenCalled();
    await act(async () => { vi.advanceTimersByTime(200); await Promise.resolve(); });
    expect(mocks.setFanCurvePoints).toHaveBeenCalledWith(A, "global", null, "cpu");
    expect(mocks.setFanCurvePoints).toHaveBeenCalledWith(B, "global", null, "gpu");
  });

  it("collapses repeated drags of one fan into a single write", async () => {
    mocks.getFanCurveState.mockResolvedValue(split);
    mocks.setFanCurvePoints.mockImplementation(async () => split);
    const { result } = renderHook(() => useFanCurve());
    await act(async () => { await Promise.resolve(); });
    act(() => { result.current.onChannelCurve("gpu", A); result.current.onChannelCurve("gpu", B); });
    await act(async () => { vi.advanceTimersByTime(200); await Promise.resolve(); });
    expect(mocks.setFanCurvePoints).toHaveBeenCalledTimes(1);
    expect(mocks.setFanCurvePoints).toHaveBeenCalledWith(B, "global", null, "gpu");
  });
});
