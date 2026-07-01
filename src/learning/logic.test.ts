import { describe, expect, it } from "vitest";
import { learningBadge } from "./logic";

describe("learningBadge", () => {
  it("in-game + telemetry on + both capabilities → learning [tdp, fans]", () => {
    expect(
      learningBadge({ inGame: true, telemetryOn: true, tdpSupported: true, fanSupported: true }),
    ).toEqual({ state: "learning", tags: ["tdp", "fans"] });
  });

  it("fan write unsupported (MSI Claw Null) → learning [tdp] only", () => {
    expect(
      learningBadge({ inGame: true, telemetryOn: true, tdpSupported: true, fanSupported: false }),
    ).toEqual({ state: "learning", tags: ["tdp"] });
  });

  it("only fans supported → learning [fans] only", () => {
    expect(
      learningBadge({ inGame: true, telemetryOn: true, tdpSupported: false, fanSupported: true }),
    ).toEqual({ state: "learning", tags: ["fans"] });
  });

  it("telemetry off (with capability, in-game) → paused, keeps tags", () => {
    expect(
      learningBadge({ inGame: true, telemetryOn: false, tdpSupported: true, fanSupported: true }),
    ).toEqual({ state: "paused", tags: ["tdp", "fans"] });
  });

  it("no game → hidden, no tags (only learns in-game)", () => {
    expect(
      learningBadge({ inGame: false, telemetryOn: true, tdpSupported: true, fanSupported: true }),
    ).toEqual({ state: "hidden", tags: [] });
  });

  it("no game even with telemetry off → hidden", () => {
    expect(
      learningBadge({ inGame: false, telemetryOn: false, tdpSupported: true, fanSupported: true }),
    ).toEqual({ state: "hidden", tags: [] });
  });

  it("in-game but device can learn nothing → hidden (never-fake)", () => {
    expect(
      learningBadge({ inGame: true, telemetryOn: true, tdpSupported: false, fanSupported: false }),
    ).toEqual({ state: "hidden", tags: [] });
  });

  it("no capability + telemetry off → still hidden", () => {
    expect(
      learningBadge({ inGame: true, telemetryOn: false, tdpSupported: false, fanSupported: false }),
    ).toEqual({ state: "hidden", tags: [] });
  });
});
