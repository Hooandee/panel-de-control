import type { AppFacts, AppKind } from "./types";

/** The parts of Steam's own stores the rules read; all optional, since builds and platforms differ. */
interface Overview {
  appid?: number; display_name?: string; app_type?: number; installed?: boolean; store_tag?: number[]; store_category?: number[];
  minutes_playtime_forever?: number; rt_last_time_played?: number; rt_original_release_date?: number; rt_steam_release_date?: number;
  rt_purchased_time?: number; size_on_disk?: string | number; steam_deck_compat_category?: number; steam_hw_compat_category_packed?: number;
  metacritic_score?: number; review_percentage?: number; display_status?: number;
  per_client_data?: { clientid?: string; installed?: boolean }[];
}
interface SteamId { GetAccountID?(): number; ConvertTo64BitString?(): string }
interface Player { m_steamid?: SteamId; m_strPlayerName?: string; m_strNickname?: string; avatar_url_medium?: string }
/** Newer clients list players directly; older ones wrap them in `m_persona`. */
type Friend = Player & { m_persona?: Player };
type FriendIdentity = { id: number; name: string; avatar?: string };

/** Steam's getters can throw while its stores are still loading. */
export function attempt<T>(read: () => T, fallback: T): T {
  try { return read(); } catch { return fallback; }
}

function friendIdentity(friend: Friend): FriendIdentity | null {
  const player = friend.m_persona ?? friend;
  try {
    const steamid = player.m_steamid;
    const id = steamid?.GetAccountID?.() ?? Number(BigInt.asUintN(32, BigInt(steamid?.ConvertTo64BitString?.() ?? "0")));
    if (!Number.isInteger(id) || id <= 0) return null;
    const avatar = typeof player.avatar_url_medium === "string" && player.avatar_url_medium.startsWith("https://") ? player.avatar_url_medium : undefined;
    const name = [friend.m_strNickname, player.m_strNickname, player.m_strPlayerName].map((value) => value?.trim()).find(Boolean) || String(id);
    return { id, name, ...(avatar ? { avatar } : {}) };
  } catch {
    return null;
  }
}

interface InstallFolder { nFolderIndex?: number; strDriveName?: string; strUserLabel?: string; vecApps?: readonly { nAppID?: number }[] }
interface Collection { id?: string; displayName?: string; allApps?: readonly Overview[]; visibleApps?: readonly Overview[] }
export interface SteamGlobals {
  appStore?: { GetAppOverviewByAppID?(id: number): Overview | undefined; m_mapStoreTagLocalization?: Map<number, string> | Record<string, string> };
  collectionStore?: {
    GetCollection?(id: string): Collection | undefined; userCollections?: readonly Collection[];
    sharedLibrariesCollections?: readonly Collection[]; allAppsCollection?: Collection;
  };
  appAchievementProgressCache?: {
    GetAchievementProgress?(id: number): number;
    m_achievementProgress?: { mapCache?: Map<number, { unlocked?: number; total?: number }> };
  };
  installFolderStore?: { AllInstallFolders?: readonly InstallFolder[] };
  SteamUIStore?: { MainRunningAppID?: number };
  friendStore?: {
    allFriends?: readonly Friend[];
    FetchOwnedGames?(accountId: number): Promise<{ setApps?: Iterable<number> } | undefined>;
  };
  MicroSDeck?: {
    CardsAndGames?: readonly [{ uid?: string; name?: string }, readonly { uid?: string | number }[]][];
    CurrentCardAndGames?: readonly [{ uid?: string; name?: string }, readonly { uid?: string | number }[]];
  };
  App?: { m_CurrentUser?: { strSteamID?: string } };
}

const SHORTCUT = 1073741824;
const KINDS: Record<number, AppKind> = { 1: "game", 8: "game", [SHORTCUT]: "shortcut", 2: "software", 4: "tool", 8192: "music", 2048: "video" };
const DEFAULT_SOURCES = ["type-games"];
const EXTENDED_SOURCES = ["type-software", "type-music", "type-tools", "type-videos"];

export const folderId = (folder: InstallFolder) => folder.strDriveName || folder.strUserLabel || String(folder.nFolderIndex ?? "");
export const userCollections = (globals: SteamGlobals) => attempt(() => globals.collectionStore?.userCollections ?? [], []);

const ids = (apps: readonly Overview[] | undefined) =>
  (apps ?? []).map((app) => app.appid).filter((id): id is number => Number.isInteger(id) && (id as number) > 0);

/** The Steam account groups belong to: its 32-bit account id, as Tab Master keys its tabs. */
export function steamAccount(globals: SteamGlobals): string | null {
  return attempt(() => {
    const id = globals.App?.m_CurrentUser?.strSteamID;
    return id && /^\d+$/.test(id) ? BigInt.asUintN(32, BigInt(id)).toString() : null;
  }, null);
}

/** A read of Steam's stores at one moment: facts per app, plus the lists rules run over. */
export interface SteamSnapshot {
  facts(appId: number): AppFacts | undefined;
  universe: number[];
  extended: number[];
  /** Cheap fingerprint of what the rules depend on; a change means the groups need another look. */
  signature: string;
}

export function readSteam(globals: SteamGlobals): SteamSnapshot {
  const store = globals.collectionStore;
  const collection = (id: string) => attempt(() => store?.GetCollection?.(id), undefined);
  const visible = (sources: string[]) => [...new Set(sources.flatMap((id) => ids(collection(id)?.visibleApps ?? collection(id)?.allApps)))];
  const shortcuts = attempt(() => (store?.allAppsCollection?.allApps ?? []).filter((app) => app.app_type === SHORTCUT), []);
  const shared = new Set(attempt(() => (store?.sharedLibrariesCollections ?? []).flatMap((c) => ids(c.allApps)), []));
  const universe = [...new Set([...visible(DEFAULT_SOURCES), ...ids(shortcuts), ...shared])];
  const inUniverse = new Set(universe);
  const extended = visible(EXTENDED_SOURCES).filter((id) => !inUniverse.has(id));

  const memberOf = new Map<number, string[]>();
  const user = userCollections(globals);
  for (const c of [...user, collection("favorite"), collection("hidden")]) {
    if (!c?.id) continue;
    for (const id of ids(c.allApps)) memberOf.set(id, [...(memberOf.get(id) ?? []), c.id]);
  }
  const folderOf = new Map<number, string>();
  for (const folder of attempt(() => globals.installFolderStore?.AllInstallFolders ?? [], [])) {
    const name = folderId(folder);
    for (const app of folder.vecApps ?? []) if (app.nAppID) folderOf.set(app.nAppID, name);
  }
  const cardOf = new Map<number, string>();
  for (const [card, games] of attempt(() => globals.MicroSDeck?.CardsAndGames ?? [], [])) {
    for (const game of games ?? []) if (card?.uid) cardOf.set(Number(game.uid), card.uid);
  }
  const current = new Set(attempt(() => globals.MicroSDeck?.CurrentCardAndGames?.[1] ?? [], []).map((game) => Number(game.uid)));
  const achievements = globals.appAchievementProgressCache;
  const cache = new Map<number, AppFacts | null>();

  const facts = (appId: number): AppFacts | undefined => {
    if (cache.has(appId)) return cache.get(appId) ?? undefined;
    const app = attempt(() => globals.appStore?.GetAppOverviewByAppID?.(appId), undefined);
    if (!app) { cache.set(appId, null); return undefined; }
    const progress = attempt(() => achievements?.m_achievementProgress?.mapCache?.get(appId), undefined);
    const percent = attempt(() => achievements?.GetAchievementProgress?.(appId) ?? 0, 0);
    const value: AppFacts = {
      appId,
      name: app.display_name ?? "",
      kind: KINDS[app.app_type ?? 1] ?? "other",
      installed: app.installed === true,
      collections: memberOf.get(appId) ?? [],
      tags: app.store_tag ?? [],
      features: app.store_category ?? [],
      playtimeMinutes: app.minutes_playtime_forever ?? 0,
      lastPlayed: app.rt_last_time_played ?? 0,
      released: app.rt_original_release_date || app.rt_steam_release_date || 0,
      purchased: app.rt_purchased_time ?? 0,
      sizeBytes: Number(app.size_on_disk ?? 0) || 0,
      deckCompat: app.steam_deck_compat_category ?? 0,
      steamosCompat: ((app.steam_hw_compat_category_packed ?? 0) >> 4) & 3,
      metacritic: app.metacritic_score ?? 0,
      reviewPercent: app.review_percentage ?? 0,
      achievementsPercent: Number.isFinite(percent) ? percent : 0,
      achievementsDone: progress?.unlocked ?? 0,
      achievementsTotal: progress?.total ?? 0,
      familyShared: shared.has(appId),
      demo: app.app_type === 8,
      comingSoon: app.display_status === 13,
      streamable: (app.per_client_data ?? []).some((client) => client.clientid !== undefined && client.clientid !== "0" && client.installed === true),
      installFolder: folderOf.get(appId) ?? null,
      sdCard: cardOf.get(appId) ?? null,
      sdCardCurrent: current.has(appId),
    };
    cache.set(appId, value);
    return value;
  };

  const installed = ids(collection("local-install")?.allApps).length;
  const signature = [
    universe.length, extended.length, installed, shared.size,
    user.map((c) => `${c.id}:${c.allApps?.length ?? 0}`).join(","),
    ids(collection("favorite")?.allApps).length, ids(collection("hidden")?.allApps).length,
    attempt(() => achievements?.m_achievementProgress?.mapCache?.size ?? 0, 0), folderOf.size, cardOf.size,
    // Playing changes play time and last played without changing any count: the running game marks it.
    attempt(() => globals.SteamUIStore?.MainRunningAppID ?? 0, 0),
  ].join("|");
  return { facts, universe, extended, signature };
}

/**
 * Friends who own each app, loaded once per session and kept for six hours. Steam answers one friend at a time,
 * so the load runs a few requests at once in the background (all of them together froze Big Picture).
 */
export function createFriendOwnership(globals: SteamGlobals, onChange: () => void, now = () => Date.now(), parallel = 3) {
  let owners: Map<number, string[]> | null = null;
  let loadedAt = 0;
  let retryAt = 0;
  let loading = false;
  // Bumped on reset and stop, so answers from an older load (another account, a dismounted Panel) are dropped.
  let generation = 0;
  let stopped = false;
  const identities = (): FriendIdentity[] => attempt(() => globals.friendStore?.allFriends ?? [], []).flatMap((friend) => friendIdentity(friend) ?? []);
  const load = () => {
    if (stopped || loading || now() < retryAt || (owners && now() - loadedAt < 6 * 3600_000)) return;
    const friends = identities();
    const fetch = globals.friendStore?.FetchOwnedGames;
    // Friends not loaded yet (or no friends): ask again later instead of deciding that nobody owns anything.
    if (!fetch || !friends.length) { retryAt = now() + 30_000; return; }
    const run = ++generation;
    loading = true;
    onChange();
    const next = new Map<number, string[]>();
    let cursor = 0, answered = 0;
    const worker = async () => {
      while (cursor < friends.length && run === generation) {
        const friend = friends[cursor++];
        try {
          const games = await fetch.call(globals.friendStore, friend.id);
          answered++;
          for (const app of games?.setApps ?? []) next.set(app, [...(next.get(app) ?? []), String(friend.id)]);
        } catch { /* a private profile or a dropped request: that friend owns nothing we can see */ }
        // Give the page a frame between answers.
        await new Promise((resolve) => setTimeout(resolve, 0));
      }
    };
    void Promise.all(Array.from({ length: Math.min(parallel, friends.length) }, worker)).finally(() => {
      if (run !== generation) return;
      loading = false;
      // Offline, every request fails: try again in a few minutes rather than caching an empty answer.
      if (answered) { owners = next; loadedAt = now(); } else retryAt = now() + 5 * 60_000;
      onChange();
    });
  };
  return {
    /** Starts the first load; until it finishes, every app reads as not known yet. */
    owners(appId: number): readonly string[] | null {
      load();
      return owners ? owners.get(appId) ?? [] : null;
    },
    loading: () => loading,
    /** Forgets everything, for another Steam account. */
    reset() { generation++; owners = null; loadedAt = 0; retryAt = 0; loading = false; },
    stop() { stopped = true; generation++; loading = false; },
    list(): { id: string; name: string; avatar?: string }[] {
      return identities().map((identity) => ({ ...identity, id: String(identity.id) })).sort((a, b) => a.name.localeCompare(b.name));
    },
  };
}
