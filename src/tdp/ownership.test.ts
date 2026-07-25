import { describe, expect, it } from "vitest";

import { ownershipView } from "./ownership";

const base = {
  status: "in_sync" as const,
  reason: "",
  requested: { pl1: 25 },
  target: { pl1: 25 },
  applied: { pl1: 25 },
  surfaces: {},
  conflict_persistent: false,
  failures: 0,
};

describe("ownershipView", () => {
  it("hides the normal synchronized state", () => {
    expect(ownershipView(base).show).toBe(false);
  });

  it("shows requested, target and applied while constrained", () => {
    expect(ownershipView({
      ...base,
      status: "constrained",
      reason: "live_max",
      target: { pl1: 15 },
      applied: { pl1: 15 },
    })).toEqual({
      show: true,
      kind: "constrained",
      requested: 25,
      target: 15,
      applied: 15,
      persistent: false,
    });
  });

  it("shows a persistent conflict even while correcting", () => {
    const view = ownershipView({
      ...base,
      status: "drift",
      conflict_persistent: true,
      applied: { pl1: 30 },
    });
    expect(view.show).toBe(true);
    expect(view.kind).toBe("conflict");
  });

  it("hides ownership status while a named firmware mode owns the rails", () => {
    expect(ownershipView({
      ...base,
      status: "unverifiable",
      reason: "firmware_mode",
    }).show).toBe(false);
  });
});
