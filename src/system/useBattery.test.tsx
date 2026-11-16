// @vitest-environment happy-dom
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { BatteryState, ChargeLimit } from "../api";

const mocks = vi.hoisted(() => ({
  getBatteryState: vi.fn(),
  setChargeLimit: vi.fn(),
  setChargeLimitFullOnce: vi.fn(),
  recordUiEvent: vi.fn(),
}));

vi.mock("../api", () => ({
  getBatteryState: mocks.getBatteryState,
  setChargeLimit: mocks.setChargeLimit,
  setChargeLimitFullOnce: mocks.setChargeLimitFullOnce,
}));

vi.mock("./uiEvents", () => ({ recordUiEvent: mocks.recordUiEvent }));

import { useBattery } from "./useBattery";
import sliderReport from "./fixtures/battery-limit-slider-report.json";

const CHARGE_LIMIT: ChargeLimit = {
  backend: "fake",
  supported: true,
  adjustable: true,
  managed: true,
  enabled: true,
  percent: 80,
  applied_percent: 80,
  min: 20,
  max: 100,
  full_charge_once: {
    available: true,
    active: false,
    status: "inactive",
    expires_at: null,
  },
};

const STATE: BatteryState = {
  battery: {
    present: true,
    percent: 70,
    status: "Charging",
    health_percent: 95,
    cycle_count: 10,
    energy_now_mwh: 30_000,
    energy_full_mwh: 40_000,
    energy_full_design_mwh: 42_000,
    power_now_w: 12,
    eta_seconds: 3_600,
    ac_online: true,
  },
  charge_limit: CHARGE_LIMIT,
};

async function settle(): Promise<void> {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("useBattery mutation ordering", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mocks.getBatteryState.mockResolvedValue(STATE);
    mocks.setChargeLimit.mockResolvedValue(CHARGE_LIMIT);
    mocks.setChargeLimitFullOnce.mockResolvedValue(CHARGE_LIMIT);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it.each(["before", "during"] as const)("preserves a confirmed choice when a poll started %s its write", async (readStarts) => {
    const before = sliderReport.confirmedWrites.find(({ readback }) => readback === 65)!;
    const chosen = sliderReport.confirmedWrites.find(({ readback }) => readback === 80)!;
    const observedLimit = (percent: number): ChargeLimit => ({
      ...CHARGE_LIMIT,
      ...sliderReport.chargeLimit,
      percent,
      applied_percent: percent,
    });
    const stale: BatteryState = {
      battery: sliderReport.battery,
      charge_limit: observedLimit(before.readback),
    };
    let resolvePoll!: (state: BatteryState) => void;
    mocks.getBatteryState.mockResolvedValueOnce(stale).mockReturnValueOnce(new Promise((resolve) => {
      resolvePoll = resolve;
    }));
    mocks.setChargeLimit.mockResolvedValueOnce(observedLimit(chosen.readback));
    const { result } = renderHook(() => useBattery());
    await settle();
    await act(async () => vi.advanceTimersByTimeAsync(readStarts === "before" ? 3000 : 2900));

    act(() => result.current.setLimit(true, chosen.requested));
    await act(async () => vi.advanceTimersByTimeAsync(250));
    await settle();
    expect(result.current.state?.charge_limit.percent).toBe(chosen.readback);

    resolvePoll(stale);
    await settle();
    expect(result.current.state?.charge_limit.percent).toBe(chosen.readback);
    expect(result.current.state?.charge_limit.applied_percent).toBe(chosen.readback);
    expect(mocks.recordUiEvent).toHaveBeenCalledWith("battery", "stale_limit_read", {
      superseded: readStarts === "before",
      pendingAtStart: readStarts === "during",
      observedPercent: before.readback,
      keptPercent: chosen.readback,
    });

    mocks.getBatteryState.mockResolvedValueOnce({
      ...stale,
      charge_limit: observedLimit(sliderReport.chargeLimit.percent),
    });
    await act(async () => vi.advanceTimersByTimeAsync(3000));
    expect(result.current.state?.charge_limit.percent).toBe(sliderReport.chargeLimit.percent);
    expect(mocks.recordUiEvent).toHaveBeenCalledTimes(1);
  });

  it("flushes a pending base-limit change before the temporary action", async () => {
    const { result } = renderHook(() => useBattery());
    await settle();

    act(() => result.current.setLimit(false, 80));
    expect(result.current.state?.charge_limit.enabled).toBe(false);
    expect(result.current.state?.charge_limit.full_charge_once.available).toBe(false);

    act(() => result.current.setFullChargeOnce(true));
    await settle();

    expect(mocks.setChargeLimit).toHaveBeenCalledWith(false, 80);
    expect(mocks.setChargeLimitFullOnce).toHaveBeenCalledWith(true);
    expect(mocks.setChargeLimit.mock.invocationCallOrder[0])
      .toBeLessThan(mocks.setChargeLimitFullOnce.mock.invocationCallOrder[0]);
  });

  it("waits for an in-flight limit write before lifting that limit", async () => {
    let resolveLimit!: (value: ChargeLimit) => void;
    mocks.setChargeLimit.mockReturnValueOnce(new Promise((resolve) => {
      resolveLimit = resolve;
    }));
    const { result } = renderHook(() => useBattery());
    await settle();

    act(() => result.current.setLimit(true, 90));
    await act(async () => vi.advanceTimersByTimeAsync(250));
    act(() => result.current.setFullChargeOnce(true));
    await settle();

    expect(mocks.setChargeLimitFullOnce).not.toHaveBeenCalled();

    await act(async () => vi.advanceTimersByTimeAsync(3000));
    expect(mocks.recordUiEvent).not.toHaveBeenCalled();

    resolveLimit({ ...CHARGE_LIMIT, percent: 90, applied_percent: 90 });
    await settle();

    expect(mocks.setChargeLimitFullOnce).toHaveBeenCalledWith(true);
  });
});
