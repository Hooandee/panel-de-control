import { describe, expect, it } from "vitest";

import { shouldReportAppid } from "./gameReport";

describe("shouldReportAppid", () => {
  it("reports a game starting", () => {
    expect(shouldReportAppid("123", null, undefined)).toBe(true);
  });

  it("does not re-report the committed game", () => {
    expect(shouldReportAppid("123", "123", undefined)).toBe(false);
  });

  it("reports the game exit (null) even though nothing is in flight", () => {
    // The regression: `null` is a real target ("no game"). When the idle sentinel was
    // also `null`, this returned false and the exit was swallowed → backend stayed
    // pinned to the last game and its per-game profile leaked into the Global view.
    expect(shouldReportAppid(null, "123", undefined)).toBe(true);
  });

  it("does not double-send while a null report is already in flight", () => {
    expect(shouldReportAppid(null, "123", null)).toBe(false);
  });

  it("does not re-send an appid already in flight", () => {
    expect(shouldReportAppid("123", null, "123")).toBe(false);
  });

  it("nothing to do when already committed to no game", () => {
    expect(shouldReportAppid(null, null, undefined)).toBe(false);
  });
});
