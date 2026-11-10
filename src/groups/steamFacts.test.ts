import { describe, expect, it, vi } from "vitest";

import { createFriendOwnership, readSteam, steamAccount, type SteamGlobals } from "./steamFacts";

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
      m_mapCollectionsFromStorage: new Map(),
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

describe("createFriendOwnership", () => {
  it("asks Steam for a few friends at a time and reports while it loads", async () => {
    let inFlight = 0, peak = 0;
    const friend = (id: number) => ({ m_steamid: { GetAccountID: () => id }, m_strPlayerName: `F${id}` });
    const globals: SteamGlobals = { friendStore: {
      allFriends: Array.from({ length: 10 }, (_, i) => friend(i + 1)),
      FetchOwnedGames: async (id: number) => {
        inFlight++; peak = Math.max(peak, inFlight);
        await new Promise((resolve) => setTimeout(resolve, 1));
        inFlight--;
        return { setApps: id % 2 ? [10] : [20] };
      },
    } };
    const changes: boolean[] = [];
    const friends = createFriendOwnership(globals, () => changes.push(friends.loading()));
    expect(friends.owners(10)).toBeNull();
    expect(friends.loading()).toBe(true);
    await vi.waitFor(() => expect(friends.loading()).toBe(false));
    expect(peak).toBeLessThanOrEqual(3);
    expect(friends.owners(10)).toEqual(["1", "3", "5", "7", "9"]);
    expect(changes).toEqual([true, false]);
  });
});

describe("friends list", () => {
  it("lists friends by name with their avatar", () => {
    const player = (id: number, name: string, avatar?: string) => ({ m_steamid: { GetAccountID: () => id }, m_strPlayerName: name, ...(avatar ? { avatar_url_medium: avatar } : {}) });
    const friends = createFriendOwnership({ friendStore: { allFriends: [player(2, "Zoe", "https://avatars.example/z.jpg"), player(1, "Ana"), player(3, "Bad", "javascript:x")] } }, () => {});
    expect(friends.list()).toEqual([{ id: "1", name: "Ana" }, { id: "3", name: "Bad" }, { id: "2", name: "Zoe", avatar: "https://avatars.example/z.jpg" }]);
  });
});

describe("friend ownership edge cases", () => {
  const player = (id: number) => ({ m_steamid: { GetAccountID: () => id }, m_strPlayerName: `F${id}` });

  it("does not decide that nobody owns anything while the friends list is still empty", async () => {
    const store: { allFriends: ReturnType<typeof player>[]; FetchOwnedGames: (id: number) => Promise<{ setApps: number[] }> } = { allFriends: [], FetchOwnedGames: async () => ({ setApps: [10] }) };
    let clock = 0;
    const friends = createFriendOwnership({ friendStore: store }, () => {}, () => clock);
    expect(friends.owners(10)).toBeNull();
    store.allFriends = [player(1)];
    clock += 31_000;
    friends.owners(10);
    await vi.waitFor(() => expect(friends.owners(10)).toEqual(["1"]));
  });

  it("retries later when every request fails, and stops for good on stop", async () => {
    let calls = 0;
    const friends = createFriendOwnership({ friendStore: { allFriends: [player(1)], FetchOwnedGames: async () => { calls++; throw new Error("offline"); } } }, () => {});
    friends.owners(10);
    await vi.waitFor(() => expect(friends.loading()).toBe(false));
    expect(friends.owners(10)).toBeNull();
    friends.stop();
    friends.reset();
    expect(calls).toBe(1);
  });

  it("drops answers from before a reset", async () => {
    let release: (v: { setApps: number[] }) => void = () => {};
    const friends = createFriendOwnership({ friendStore: { allFriends: [player(1)], FetchOwnedGames: () => new Promise((resolve) => { release = resolve; }) } }, () => {});
    friends.owners(10);
    friends.reset();
    release({ setApps: [10] });
    await new Promise((resolve) => setTimeout(resolve, 5));
    expect(friends.loading()).toBe(false);
  });
});

describe("Steam's collections before they load", () => {
  it("never touches Steam's userCollections until the store holds its collections", async () => {
    const { userCollections } = await import("./steamFacts");
    const getter = vi.fn(() => { throw new TypeError("Cannot read properties of undefined (reading 'values')"); });
    const store: Record<string, unknown> = {};
    Object.defineProperty(store, "userCollections", { get: getter });
    expect(userCollections({ collectionStore: store } as unknown as SteamGlobals)).toEqual([]);
    expect(getter).not.toHaveBeenCalled();
    const loaded = [{ id: "uc-1", displayName: "Favs" }];
    const ready = { m_mapCollectionsFromStorage: new Map([["uc-1", loaded[0]]]), userCollections: loaded };
    expect(userCollections({ collectionStore: ready } as unknown as SteamGlobals)).toEqual(loaded);
  });
});
