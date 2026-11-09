import { describe, expect, it } from "vitest";

import { readSteam, steamAccount, type SteamGlobals } from "./steamFacts";

const o = (appid: number, over: Record<string, unknown> = {}) => ({ appid, display_name: `A${appid}`, app_type: 1, ...over });

function globals(): SteamGlobals {
  const apps = [
    o(1, { installed: true, store_tag: [5], store_category: [28], minutes_playtime_forever: 90, rt_last_time_played: 100,
      rt_original_release_date: 0, rt_steam_release_date: 50, size_on_disk: "2000", steam_deck_compat_category: 3,
      steam_hw_compat_category_packed: 2 << 4, metacritic_score: 80, review_percentage: 70, display_status: 13,
      per_client_data: [{ clientid: "0", installed: true }, { clientid: "42", installed: true }] }),
    o(2, { app_type: 8 }),
    o(3, { app_type: 1073741824, installed: true }),
    o(4, { app_type: 8192 }),
    o(5),
  ];
  const byId = new Map(apps.map((a) => [a.appid, a]));
  return {
    App: { m_CurrentUser: { strSteamID: "76561197960287930" } },
    appStore: { GetAppOverviewByAppID: (id) => byId.get(id) },
    collectionStore: {
      GetCollection: (id) => ({ "type-games": { visibleApps: [apps[0], apps[1]] }, "type-music": { visibleApps: [apps[3]] }, favorite: { id: "favorite", allApps: [apps[0]] } } as unknown as Record<string, never>)[id],
      userCollections: [{ id: "uc-1", allApps: [apps[1]] }],
      sharedLibrariesCollections: [{ allApps: [apps[4]] }],
      allAppsCollection: { allApps: apps },
    },
    appAchievementProgressCache: { GetAchievementProgress: (id) => (id === 1 ? 50 : 0), m_achievementProgress: { mapCache: new Map([[1, { unlocked: 5, total: 10 }]]) } },
    installFolderStore: { AllInstallFolders: [{ nFolderIndex: 1, strDriveName: "SD", vecApps: [{ nAppID: 3 }] }] },
    MicroSDeck: { CardsAndGames: [[{ uid: "card-a" }, [{ uid: 3 }]]], CurrentCardAndGames: [{ uid: "card-a" }, [{ uid: 3 }]] },
  };
}

describe("readSteam", () => {
  it("builds the universe from games, shortcuts and family-shared apps, and keeps others apart", () => {
    const steam = readSteam(globals());
    expect(steam.universe).toEqual([1, 2, 3, 5]);
    expect(steam.extended).toEqual([4]);
  });

  it("reads every fact the rules need", () => {
    const steam = readSteam(globals());
    expect(steam.facts(1)).toMatchObject({
      kind: "game", installed: true, collections: ["favorite"], tags: [5], features: [28], playtimeMinutes: 90, lastPlayed: 100,
      released: 50, sizeBytes: 2000, deckCompat: 3, steamosCompat: 2, metacritic: 80, reviewPercent: 70, comingSoon: true,
      streamable: true, achievementsPercent: 50, achievementsDone: 5, achievementsTotal: 10,
    });
    expect(steam.facts(2)).toMatchObject({ kind: "game", demo: true, collections: ["uc-1"] });
    expect(steam.facts(3)).toMatchObject({ kind: "shortcut", installFolder: "SD", sdCard: "card-a", sdCardCurrent: true });
    expect(steam.facts(4)?.kind).toBe("music");
    expect(steam.facts(5)?.familyShared).toBe(true);
    expect(steam.facts(99)).toBeUndefined();
  });

  it("the account is the 32-bit account id", () => {
    expect(steamAccount(globals())).toBe("22202");
    expect(steamAccount({})).toBeNull();
  });

  it("survives stores that throw", () => {
    const broken: SteamGlobals = { collectionStore: { GetCollection: () => { throw new TypeError("forEach"); }, get userCollections(): never { throw new Error("x"); } } };
    expect(readSteam(broken).universe).toEqual([]);
  });
});
