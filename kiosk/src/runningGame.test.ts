import { describe, expect, it, vi } from "vitest";

vi.mock("../../src/api", () => ({ getTdpState: vi.fn(), getKioskGame: vi.fn() }));

import { stableGameKey } from "../../src/tdp/gameIdentity";
import { overviewForKey } from "./runningGame";

describe("overviewForKey", () => {
  it("round-trips Steam and non-Steam keys through stableGameKey", () => {
    expect(stableGameKey(overviewForKey("413150", "Stardew Valley")!)).toBe("413150");
    expect(stableGameKey(overviewForKey("ns:retroarch", null)!)).toBe("ns:retroarch");
  });

  it("reports no game when the backend has none", () => {
    expect(overviewForKey(null, null)).toBeUndefined();
  });
});
