// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({
  ToggleField: ({ label, description, checked, disabled, onChange }: {
    label: ReactNode;
    description?: ReactNode;
    checked: boolean;
    disabled?: boolean;
    onChange: (checked: boolean) => void;
  }) => (
    <label>
      <span>{label}</span>
      <span>{description}</span>
      <input
        aria-label={String(label)}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.currentTarget.checked)}
      />
    </label>
  ),
  SliderField: ({ disabled }: { disabled?: boolean }) => <input type="range" disabled={disabled} />,
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
    full_charge_once: {
      available: true,
      active: false,
      status: "inactive",
      expires_at: null,
    },
  },
};

describe("BatteryCard charge-limit ownership", () => {
  afterEach(cleanup);

  it("keeps the active marker when the eye only hides the controls", () => {
    const { container } = render(
      <BatteryCard state={STATE} onSetLimit={vi.fn()} onSetFullChargeOnce={vi.fn()} hideLimitControl />,
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
      <BatteryCard state={state} onSetLimit={vi.fn()} onSetFullChargeOnce={vi.fn()} />,
    );

    expect(screen.queryByText("system.battery.limit")).toBeNull();
    expect(container.querySelector('[data-pdc-charge-limit-marker="true"]')).toBeNull();
  });

  it("keeps controls visible when only the frontend module cache is stale", () => {
    const { container } = render(
      <BatteryCard {...{ limitManaged: false }} state={STATE} onSetLimit={vi.fn()} onSetFullChargeOnce={vi.fn()} />,
    );

    expect(screen.getByText("system.battery.limit")).not.toBeNull();
    expect(container.querySelector('[data-pdc-charge-limit-marker="true"]')).not.toBeNull();
  });

  it("offers one-time full charge as an explicit off toggle", () => {
    const onSetFullChargeOnce = vi.fn();
    render(
      <BatteryCard
        state={STATE}
        onSetLimit={vi.fn()}
        onSetFullChargeOnce={onSetFullChargeOnce}
      />,
    );

    const toggle = screen.getByRole("checkbox", {
      name: "system.battery.fullOnce.title",
    }) as HTMLInputElement;
    expect(toggle.checked).toBe(false);
    expect(screen.getByText("system.battery.fullOnce.ready")).not.toBeNull();
    fireEvent.click(toggle);
    expect(onSetFullChargeOnce).toHaveBeenCalledWith(true);
  });

  it("shows the temporary mode on and locks the saved limit", () => {
    const onSetFullChargeOnce = vi.fn();
    const state = {
      ...STATE,
      charge_limit: {
        ...STATE.charge_limit,
        full_charge_once: {
          ...STATE.charge_limit.full_charge_once,
          active: true,
          status: "active" as const,
          expires_at: 87_400,
        },
      },
    };
    render(
      <BatteryCard
        state={state}
        onSetLimit={vi.fn()}
        onSetFullChargeOnce={onSetFullChargeOnce}
      />,
    );

    const toggle = screen.getByRole("checkbox", {
      name: "system.battery.fullOnce.title",
    }) as HTMLInputElement;
    expect(toggle.checked).toBe(true);
    expect((screen.getByRole("slider") as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByText("system.battery.fullOnce.active")).not.toBeNull();
    fireEvent.click(toggle);
    expect(onSetFullChargeOnce).toHaveBeenCalledWith(false);
  });

  it("hides the one-time action when capability is unavailable", () => {
    const state = {
      ...STATE,
      charge_limit: {
        ...STATE.charge_limit,
        full_charge_once: {
          ...STATE.charge_limit.full_charge_once,
          available: false,
        },
      },
    };
    render(
      <BatteryCard
        state={state}
        onSetLimit={vi.fn()}
        onSetFullChargeOnce={vi.fn()}
      />,
    );

    expect(screen.queryByText("system.battery.fullOnce.title")).toBeNull();
  });
});
