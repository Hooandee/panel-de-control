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

  it("hides a secondary-rail constraint when sustained power matches", () => {
    expect(ownershipView({
      ...base,
      status: "constrained",
      reason: "safe_min",
      requested: { pl1: 15, pl2: 15, pl3: 15 },
      target: { pl1: 15, pl2: 15, pl3: 20 },
      applied: { pl1: 15, pl2: 15, pl3: 20 },
    }).show).toBe(false);
  });

  it.each(["safe_min", "live_min"])(
    "hides the stable %s sustained-floor constraint covered by the inline firmware notice",
    (reason) => {
      expect(ownershipView({
        ...base,
        status: "constrained",
        reason,
        requested: { pl1: 3, pl2: 3, pl3: 3 },
        target: { pl1: 5, pl2: 15, pl3: 20 },
        applied: { pl1: 5, pl2: 15, pl3: 20 },
      }, 5).show).toBe(false);
    },
  );

  it("shows a dynamic minimum above the physical floor because the inline notice is absent", () => {
    expect(ownershipView({
      ...base,
      status: "constrained",
      reason: "live_min",
      requested: { pl1: 6, pl2: 15, pl3: 20 },
      target: { pl1: 10, pl2: 15, pl3: 20 },
      applied: { pl1: 10, pl2: 15, pl3: 20 },
    }, 5).show).toBe(true);
  });

  it("shows a dynamic floor above the physical minimum alongside the inline notice", () => {
    expect(ownershipView({
      ...base,
      status: "constrained",
      reason: "live_min",
      requested: { pl1: 3, pl2: 15, pl3: 20 },
      target: { pl1: 10, pl2: 15, pl3: 20 },
      applied: { pl1: 10, pl2: 15, pl3: 20 },
    }, 5).show).toBe(true);
  });

  it("shows a secondary ceiling while the sustained rail is at the physical floor", () => {
    expect(ownershipView({
      ...base,
      status: "constrained",
      reason: "safe_min",
      requested: { pl1: 3, pl2: 3, pl3: 100 },
      target: { pl1: 5, pl2: 15, pl3: 49 },
      applied: { pl1: 5, pl2: 15, pl3: 49 },
    }, 5).show).toBe(true);
  });

  it("shows a minimum constraint until every target rail is confirmed", () => {
    expect(ownershipView({
      ...base,
      status: "constrained",
      reason: "live_min",
      requested: { pl1: 3, pl2: 3, pl3: 3 },
      target: { pl1: 5, pl2: 15, pl3: 20 },
      applied: { pl1: 5, pl2: 14, pl3: 20 },
    }, 5).show).toBe(true);
  });

  it("keeps showing a sustained-floor constraint until the target is confirmed", () => {
    expect(ownershipView({
      ...base,
      status: "constrained",
      reason: "live_min",
      requested: { pl1: 3, pl2: 3, pl3: 3 },
      target: { pl1: 5, pl2: 15, pl3: 20 },
      applied: { pl1: 4, pl2: 15, pl3: 20 },
    }, 5).show).toBe(true);
  });

  it("shows a persistent conflict despite a secondary-rail constraint", () => {
    const view = ownershipView({
      ...base,
      status: "constrained",
      reason: "safe_min",
      requested: { pl1: 15, pl2: 15, pl3: 15 },
      target: { pl1: 15, pl2: 15, pl3: 20 },
      applied: { pl1: 15, pl2: 15, pl3: 20 },
      conflict_persistent: true,
    });

    expect(view.show).toBe(true);
    expect(view.kind).toBe("conflict");
  });

  it.each(["safe_max", "live_max"])(
    "shows a secondary-rail %s constraint",
    (reason) => {
      const view = ownershipView({
        ...base,
        status: "constrained",
        reason,
        requested: { pl1: 15, pl2: 30, pl3: 30 },
        target: { pl1: 15, pl2: 20, pl3: 25 },
        applied: { pl1: 15, pl2: 20, pl3: 25 },
      });

      expect(view.show).toBe(true);
      expect(view.kind).toBe("constrained");
    },
  );

  it("shows a mixed secondary floor and ceiling constraint", () => {
    const view = ownershipView({
      ...base,
      status: "constrained",
      reason: "safe_min",
      requested: { pl1: 5, pl2: 5, pl3: 100 },
      target: { pl1: 5, pl2: 15, pl3: 49 },
      applied: { pl1: 5, pl2: 15, pl3: 49 },
    });

    expect(view.show).toBe(true);
    expect(view.kind).toBe("constrained");
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
