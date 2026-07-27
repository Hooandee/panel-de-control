import { describe, expect, it } from "vitest";

import { isSameGameReport, shouldReportGame } from "./gameReport";

const report = (appid: string | null, name: string | null = null) => ({ appid, name });

describe("shouldReportGame", () => {
  it("reports a game starting", () => {
    expect(shouldReportGame(report("123", "Game"), report(null), undefined)).toBe(true);
  });

  it("does not re-report the committed game", () => {
    expect(shouldReportGame(report("123", "Game"), report("123", "Game"), undefined)).toBe(false);
  });

  it("reports the game exit (null) even though nothing is in flight", () => {
    // The regression: `null` is a real target ("no game"). When the idle sentinel was
    // also `null`, this returned false and the exit was swallowed → backend stayed
    // pinned to the last game and its per-game profile leaked into the Global view.
    expect(shouldReportGame(report(null), report("123", "Game"), undefined)).toBe(true);
  });

  it("does not double-send while a null report is already in flight", () => {
    expect(shouldReportGame(report(null), report("123", "Game"), report(null))).toBe(false);
  });

  it("does not re-send an appid already in flight", () => {
    expect(shouldReportGame(report("123", "Game"), report(null), report("123", "Game"))).toBe(false);
  });

  it("nothing to do when already committed to no game", () => {
    expect(shouldReportGame(report(null), report(null), undefined)).toBe(false);
  });

  it("reports a hydrated display name without changing the profile identity", () => {
    expect(shouldReportGame(
      report("123", "Actual name"),
      report("123", "123"),
      undefined,
    )).toBe(true);
  });

  it("recognises whether a late response still belongs to the current request", () => {
    expect(isSameGameReport(report("2", "B"), report("1", "A"))).toBe(false);
    expect(isSameGameReport(report("2", "B"), report("2", "B"))).toBe(true);
  });
});
