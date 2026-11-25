import { afterEach, describe, expect, it, vi } from "vitest";

import { createThemeGamesAccess } from "./gamesAccess";

describe("theme games access", () => {
  it("asks Panel to force close by decimal app id and passes its result through", async () => {
    const forceClose = vi.fn(async () => ({ result: "killed", appid: 4049170, processes: 4, killed: 2 }));
    const games = createThemeGamesAccess({ forceClose });
    expect(await games.forceClose!(4049170)).toBe("killed");
    expect(await games.forceClose!("12884901888000000000")).toBe("killed");
    expect(forceClose).toHaveBeenNthCalledWith(1, "4049170");
    expect(forceClose).toHaveBeenNthCalledWith(2, "12884901888000000000");
    expect(Object.isFrozen(games)).toBe(true);
  });

  it("refuses malformed ids without calling Panel", async () => {
    const forceClose = vi.fn(async () => ({ result: "terminated" }));
    const games = createThemeGamesAccess({ forceClose });
    for (const appid of [0, -3, 1.5, Number.MAX_SAFE_INTEGER + 2, "", "01", "12a", "1".repeat(21)]) {
      expect(await games.forceClose!(appid)).toBe("failed");
    }
    expect(forceClose).not.toHaveBeenCalled();
  });

  it("never rejects", async () => {
    expect(await createThemeGamesAccess({ forceClose: async () => { throw new Error("gone"); } }).forceClose!(10))
      .toBe("unavailable");
    expect(await createThemeGamesAccess({ forceClose: async () => ({ result: "exploded" }) }).forceClose!(10))
      .toBe("failed");
    expect(await createThemeGamesAccess({ forceClose: async () => null }).forceClose!(10)).toBe("failed");
  });

  describe("pause", () => {
    const steam = globalThis as { SteamUIStore?: { MainRunningAppID?: unknown } };
    afterEach(() => { delete steam.SteamUIStore; });

    it("freezes the game Steam has in front, shortcuts included, and thaws on resume", async () => {
      const pause = vi.fn(async () => true);
      const resume = vi.fn(async () => {});
      const games = createThemeGamesAccess({ forceClose: vi.fn(), pause, resume });
      steam.SteamUIStore = { MainRunningAppID: 292030 };
      expect(await games.pause(1000.4)).toBe(true);
      steam.SteamUIStore = { MainRunningAppID: "12884901888000000000" };
      expect(await games.pause(500)).toBe(true);
      expect(pause).toHaveBeenNthCalledWith(1, "292030", 1000);
      expect(pause).toHaveBeenNthCalledWith(2, "12884901888000000000", 500);
      await games.resume();
      expect(resume).toHaveBeenCalledTimes(1);
    });

    it("is false without a game, a usable time or a Panel that can freeze", async () => {
      const pause = vi.fn(async () => true);
      expect(await createThemeGamesAccess({ forceClose: vi.fn(), pause }).pause(1000)).toBe(false);
      steam.SteamUIStore = { MainRunningAppID: 292030 };
      expect(await createThemeGamesAccess({ forceClose: vi.fn(), pause }).pause(0)).toBe(false);
      expect(await createThemeGamesAccess({ forceClose: vi.fn() }).pause(1000)).toBe(false);
      expect(await createThemeGamesAccess({ forceClose: vi.fn(), pause: async () => { throw new Error("gone"); } }).pause(1000)).toBe(false);
      await createThemeGamesAccess({ forceClose: vi.fn(), resume: async () => { throw new Error("gone"); } }).resume();
      expect(pause).not.toHaveBeenCalled();
    });
  });
});

describe("theme games howLongToBeat", () => {
  it("asks Panel by decimal id and hands back hours", async () => {
    const howLongToBeat = vi.fn(async () => ({ result: "found", main: 27, plus: 41.6, complete: 65.6, title: "Hollow Knight" }));
    const games = createThemeGamesAccess({ forceClose: vi.fn(), howLongToBeat });
    expect(await games.howLongToBeat(367520, " Hollow Knight ")).toEqual({ main: 27, plus: 41.6, complete: 65.6 });
    expect(howLongToBeat).toHaveBeenCalledWith("367520", "Hollow Knight");
  });

  it("gives null for misses, failures, junk and an older Panel", async () => {
    const reply = (value: unknown) => createThemeGamesAccess({ forceClose: vi.fn(), howLongToBeat: async () => value });
    expect(await reply({ result: "not_found" }).howLongToBeat(1, "x")).toBeNull();
    expect(await reply({ result: "found", main: "27", plus: -1, complete: null }).howLongToBeat(1, "x")).toBeNull();
    expect(await createThemeGamesAccess({ forceClose: vi.fn(), howLongToBeat: async () => { throw new Error("gone"); } }).howLongToBeat(1, "x")).toBeNull();
    expect(await createThemeGamesAccess({ forceClose: vi.fn() }).howLongToBeat(1, "x")).toBeNull();
    const asked = vi.fn();
    const games = createThemeGamesAccess({ forceClose: vi.fn(), howLongToBeat: asked });
    expect(await games.howLongToBeat("01", "x")).toBeNull();
    expect(await games.howLongToBeat(1, "  ")).toBeNull();
    expect(asked).not.toHaveBeenCalled();
  });
});

describe("theme games protonDb", () => {
  it("passes a known tier through and refuses the rest", async () => {
    const protonDb = vi.fn(async () => ({ result: "found", tier: "gold", confidence: "good", total: 120 }));
    expect(await createThemeGamesAccess({ forceClose: vi.fn(), protonDb }).protonDb(292030)).toEqual({ tier: "gold", total: 120 });
    expect(protonDb).toHaveBeenCalledWith("292030");
    const reply = (value: unknown) => createThemeGamesAccess({ forceClose: vi.fn(), protonDb: async () => value });
    expect(await reply({ result: "found", tier: "pending" }).protonDb(1)).toBeNull();
    expect(await reply({ result: "not_found" }).protonDb(1)).toBeNull();
    expect(await createThemeGamesAccess({ forceClose: vi.fn() }).protonDb(1)).toBeNull();
  });
});
