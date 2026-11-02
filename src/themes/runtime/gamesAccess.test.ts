import { describe, expect, it, vi } from "vitest";

import { createThemeGamesAccess } from "./gamesAccess";

describe("theme games access", () => {
  it("asks Panel to force close by decimal app id and passes its result through", async () => {
    const forceClose = vi.fn(async () => ({ result: "killed", appid: 4049170, processes: 4, killed: 2 }));
    const games = createThemeGamesAccess({ forceClose });
    expect(await games.forceClose(4049170)).toBe("killed");
    expect(await games.forceClose("12884901888000000000")).toBe("killed");
    expect(forceClose).toHaveBeenNthCalledWith(1, "4049170");
    expect(forceClose).toHaveBeenNthCalledWith(2, "12884901888000000000");
    expect(Object.isFrozen(games)).toBe(true);
  });

  it("refuses malformed ids without calling Panel", async () => {
    const forceClose = vi.fn(async () => ({ result: "terminated" }));
    const games = createThemeGamesAccess({ forceClose });
    for (const appid of [0, -3, 1.5, Number.MAX_SAFE_INTEGER + 2, "", "01", "12a", "1".repeat(21)]) {
      expect(await games.forceClose(appid)).toBe("failed");
    }
    expect(forceClose).not.toHaveBeenCalled();
  });

  it("never rejects", async () => {
    expect(await createThemeGamesAccess({ forceClose: async () => { throw new Error("gone"); } }).forceClose(10))
      .toBe("unavailable");
    expect(await createThemeGamesAccess({ forceClose: async () => ({ result: "exploded" }) }).forceClose(10))
      .toBe("failed");
    expect(await createThemeGamesAccess({ forceClose: async () => null }).forceClose(10)).toBe("failed");
  });
});
