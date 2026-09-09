// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({
  ToggleField: ({ label }: { label: ReactNode }) => <label>{label}<input type="checkbox" /></label>,
  SliderField: () => <input type="range" />,
}));

vi.mock("../i18n", () => ({
  useI18n: () => ({ t: (key: string) => key }),
}));

import type { BatteryState } from "../api";
import { BatteryCard } from "./BatteryCard";

const STATE: BatteryState = {
  battery: {
    present: true,
    percent: 73,
    status: "Charging",
    health_percent: 96,
    cycle_count: 42,
    energy_now_mwh: 28000,
    energy_full_mwh: 38000,
    energy_full_design_mwh: 40000,
    power_now_w: 12,
    eta_seconds: 3600,
    ac_online: true,
  },
  charge_limit: {
    backend: "fake",
    supported: true,
    adjustable: true,
    managed: true,
    enabled: true,
    percent: 80,
    applied_percent: 80,
    min: 20,
    max: 100,
  },
};

describe("BatteryCard charge-limit ownership", () => {
  afterEach(cleanup);

  it("keeps the active marker when the eye only hides the controls", () => {
    const { container } = render(
      <BatteryCard state={STATE} onSetLimit={vi.fn()} hideLimitControl />,
    );

    expect(screen.queryByText("system.battery.limit")).toBeNull();
    expect(container.querySelector('[data-pdc-charge-limit-marker="true"]')).not.toBeNull();
  });

  it("removes controls and marker when Panel de Control steps aside", () => {
    const state = {
      ...STATE,
      charge_limit: { ...STATE.charge_limit, managed: false },
    };
    const { container } = render(
      <BatteryCard state={state} onSetLimit={vi.fn()} />,
    );

    expect(screen.queryByText("system.battery.limit")).toBeNull();
    expect(container.querySelector('[data-pdc-charge-limit-marker="true"]')).toBeNull();
  });

  it("keeps controls visible when only the frontend module cache is stale", () => {
    const { container } = render(
      <BatteryCard {...{ limitManaged: false }} state={STATE} onSetLimit={vi.fn()} />,
    );

    expect(screen.getByText("system.battery.limit")).not.toBeNull();
    expect(container.querySelector('[data-pdc-charge-limit-marker="true"]')).not.toBeNull();
  });
});
