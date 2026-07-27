import { describe, expect, it } from "vitest";
import { activeCountFromRaw, hydrateUnknownCounts } from "./gameList";

describe("activeCountFromRaw", () => {
  it("keeps an uncached value unknown", () => {
    expect(activeCountFromRaw(null)).toBeNull();
  });

  it("counts known active pills", () => {
    expect(activeCountFromRaw("mangohud %command% -novid")).toBe(2);
  });

  it("does not claim a count for a malformed string", () => {
    expect(activeCountFromRaw("echo prep\n%command%")).toBeNull();
  });
});

describe("hydrateUnknownCounts", () => {
  it("hydrates uncached rows with bounded concurrency", async () => {
    const games = [1, 2, 3, 4].map((liveAppid) => ({ liveAppid, activeCount: null }));
    const results = new Map<number, number | null>();
    let active = 0;
    let peak = 0;
    await hydrateUnknownCounts(
      games,
      async (appid) => {
        active += 1;
        peak = Math.max(peak, active);
        await Promise.resolve();
        active -= 1;
        return { launch: appid % 2 ? "%command% -novid" : "" };
      },
      (appid, count) => results.set(appid, count),
      2,
    );
    expect(peak).toBe(2);
    expect([...results.entries()]).toEqual([
      [1, 1],
      [2, 0],
      [3, 1],
      [4, 0],
    ]);
  });
});
