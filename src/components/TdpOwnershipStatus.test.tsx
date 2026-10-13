// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../i18n", () => ({
  useI18n: () => ({
    t: (key: string, vars?: Record<string, unknown>) =>
      vars ? `${key} ${Object.values(vars).join(" ")}` : key,
  }),
}));

import { TdpOwnershipStatus } from "./TdpOwnershipStatus";

const ownership = {
  status: "constrained" as const,
  reason: "power_source_limit",
  requested: { pl1: 22 },
  target: { pl1: 22 },
  applied: { pl1: 15 },
  surfaces: {},
  conflict_persistent: false,
  failures: 0,
};

function silent(props: Parameters<typeof TdpOwnershipStatus>[0]) {
  const { container } = render(<TdpOwnershipStatus {...props} />);
  const empty = container.textContent === "";
  cleanup();
  return empty;
}

describe("TdpOwnershipStatus", () => {
  afterEach(cleanup);

  it("blames the charger when it cannot supply the requested power", () => {
    render(<TdpOwnershipStatus ownership={ownership} onAc />);

    expect(screen.getByText("tdp.ownership.powerLimited 15")).toBeTruthy();
  });

  it("says the device is limiting power away from AC", () => {
    render(<TdpOwnershipStatus ownership={ownership} onAc={false} />);

    expect(screen.getByText("tdp.ownership.constrained 15")).toBeTruthy();
  });

  it("says the device refused the value and where it stayed", () => {
    render(<TdpOwnershipStatus ownership={{ ...ownership, status: "rejected", reason: "write_failed", applied: { pl1: 20 }, target: { pl1: 33 } }} />);

    expect(screen.getByText("tdp.ownership.rejected 33 20")).toBeTruthy();
  });

  it("drops the unknown current value from a refusal instead of printing a dash", () => {
    render(<TdpOwnershipStatus ownership={{ ...ownership, status: "rejected", reason: "write_failed", applied: {}, target: { pl1: 33 } }} />);

    expect(screen.getByText("tdp.ownership.rejectedNoValue 33")).toBeTruthy();
  });

  it("says the device is ignoring the limit when power stays above it", () => {
    render(
      <TdpOwnershipStatus
        ownership={{
          ...ownership,
          status: "in_sync",
          reason: "",
          overshoot: { state: "unresolved", target_w: 20, peak_w: 43, age_s: 5 },
        }}
      />,
    );

    expect(screen.getByText("tdp.ownership.overshootUnresolved 20")).toBeTruthy();
  });

  it("stays silent for states that work or fix themselves", () => {
    const base = { ...ownership, reason: "" };
    expect(silent({ ownership: { ...base, status: "in_sync" } })).toBe(true);
    expect(silent({ ownership: { ...base, status: "unverifiable", target: { pl1: 33 } } })).toBe(true);
    expect(silent({ ownership: { ...base, status: "settling" } })).toBe(true);
    expect(silent({ ownership: { ...base, status: "drift", reason: "external_drift", conflict_persistent: true } })).toBe(true);
    for (const state of ["correcting", "restored"] as const) {
      expect(silent({ ownership: { ...base, status: "in_sync", overshoot: { state, target_w: 20, peak_w: 43, age_s: 1 } } })).toBe(true);
    }
  });

  it("does not explain boost rails held at the firmware minimum", () => {
    expect(silent({
      ownership: {
        ...ownership,
        reason: "safe_min",
        requested: { pl1: 5, pl2: 5, pl3: 5 },
        target: { pl1: 5, pl2: 15, pl3: 20 },
        applied: { pl1: 5, pl2: 15, pl3: 20 },
        menu_floor: true,
      },
    })).toBe(true);
  });
});
