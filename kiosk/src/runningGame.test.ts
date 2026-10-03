import { describe, expect, it, vi } from "vitest";

vi.mock("../../src/api", () => ({ getKioskGame: vi.fn(async (appid: string) => ({ appid, name: "Stardew Valley" })) }));

import { stableGameKey } from "../../src/tdp/gameIdentity";
import { getKioskGame } from "../../src/api";
import { noteRunningGame, overviewForKey, runningAppOverview } from "./runningGame";

describe("overviewForKey", () => {
  it("round-trips Steam and non-Steam keys through stableGameKey", () => {
    expect(stableGameKey(overviewForKey("413150", "Stardew Valley")!)).toBe("413150");
    expect(stableGameKey(overviewForKey("ns:retroarch", null)!)).toBe("ns:retroarch");
  });

  it("reports no game when the backend has none", () => {
    expect(overviewForKey(null, null)).toBeUndefined();
  });
});

describe("noteRunningGame", () => {
  it("names the game once and follows the backend's key", async () => {
    noteRunningGame("413150");
    noteRunningGame("413150");
    await Promise.resolve();
    await Promise.resolve();
    expect(getKioskGame).toHaveBeenCalledTimes(1);
    expect(runningAppOverview()?.display_name).toBe("Stardew Valley");
    noteRunningGame(null);
    expect(runningAppOverview()).toBeUndefined();
  });
});
