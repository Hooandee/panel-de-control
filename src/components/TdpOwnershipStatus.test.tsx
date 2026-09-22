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

describe("TdpOwnershipStatus", () => {
  afterEach(cleanup);

  it("explains an AC power-source limit without discarding the request", () => {
    render(<TdpOwnershipStatus ownership={ownership} onAc />);

    expect(screen.getByText("tdp.ownership.powerLimited 22 22 15")).toBeTruthy();
  });

  it("keeps the generic constrained message away from AC", () => {
    render(<TdpOwnershipStatus ownership={ownership} onAc={false} />);

    expect(screen.getByText("tdp.ownership.constrained 22 22 15")).toBeTruthy();
  });
});
