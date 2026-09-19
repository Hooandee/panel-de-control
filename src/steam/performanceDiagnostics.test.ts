import { beforeEach, describe, expect, it } from "vitest";

import {
  recordSteamPerformanceDiagnostic,
  resetSteamPerformanceDiagnostics,
  steamPerformanceDiagnostics,
  steamPerformanceError,
} from "./performanceDiagnostics";

describe("Steam performance diagnostics", () => {
  beforeEach(resetSteamPerformanceDiagnostics);

  it("deduplicates unchanged state and keeps the latest 24 transitions", () => {
    recordSteamPerformanceDiagnostic("profile", { game_id: 1 });
    recordSteamPerformanceDiagnostic("profile", { game_id: 1 });
    for (let gameId = 2; gameId <= 30; gameId += 1) {
      recordSteamPerformanceDiagnostic("profile", { game_id: gameId });
    }

    const snapshot = steamPerformanceDiagnostics();
    expect(snapshot).toMatchObject({
      schema: 1,
      current: { profile: { game_id: 30 } },
    });
    expect(snapshot?.events).toHaveLength(24);
    expect(snapshot?.events[0]).toMatchObject({
      sequence: 7,
      area: "profile",
      data: { game_id: 7 },
    });
    expect(snapshot?.events[23]).toMatchObject({
      sequence: 30,
      area: "profile",
      data: { game_id: 30 },
    });
  });

  it("normalizes and bounds exception text", () => {
    expect(steamPerformanceError(new TypeError(`  ${"x".repeat(300)}\n`))).toEqual({
      name: "TypeError",
      message: "x".repeat(240),
    });
  });

  it("never throws while reading a hostile exception", () => {
    const error = Object.create(Error.prototype, {
      name: { get() { throw new Error("name unavailable"); } },
      message: { get() { throw new Error("message unavailable"); } },
    });

    expect(() => steamPerformanceError(error)).not.toThrow();
    expect(steamPerformanceError(error)).toEqual({
      name: "UnknownError",
      message: "unreadable thrown value",
    });
  });

  it("bounds every string before retaining it", () => {
    recordSteamPerformanceDiagnostic("profile", { running_game_id: "x".repeat(500) });

    expect(steamPerformanceDiagnostics()?.current.profile.running_game_id)
      .toBe("x".repeat(240));
  });
});
