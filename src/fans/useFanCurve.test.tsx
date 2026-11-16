// @vitest-environment happy-dom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
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
