import { afterEach, describe, expect, it, vi } from "vitest";

import { createGroupsClient, type GroupsHost } from "./groupsClient";
import type { SteamGlobals } from "./steamFacts";
import type { GroupDefinition } from "./types";

const STEAM64 = "76561197960287930"; // account id 22202
const overview = (appid: number, over: Record<string, unknown> = {}) => ({ appid, display_name: `G${appid}`, app_type: 1, installed: false, ...over });
const APPS = [overview(10, { installed: true, store_tag: [122] }), overview(20), overview(30, { installed: true })];

function globals(user = STEAM64): SteamGlobals {
  const byId = new Map(APPS.map((a) => [a.appid, a]));
  return {
    App: { m_CurrentUser: { strSteamID: user } },
    appStore: { GetAppOverviewByAppID: (id) => byId.get(id), m_mapStoreTagLocalization: { 122: "RPG" } },
    collectionStore: {
      GetCollection: (id) => (id === "type-games" ? { visibleApps: APPS } : id === "local-install" ? { allApps: APPS.filter((a) => a.installed) } : undefined),
      userCollections: [{ id: "uc-1", displayName: "Mine", allApps: [APPS[1]] }],
      allAppsCollection: { allApps: APPS },
    },
  };
}

function memoryHost(initial: Record<string, unknown[]> = {}): GroupsHost & { stored: Record<string, unknown[]>; fail: boolean } {
  const host = {
    stored: { ...initial },
    fail: false,
    read: vi.fn(async (account: string) => host.stored[account] ?? []),
    write: vi.fn(async (account: string, groups: GroupDefinition[]) => {
      if (host.fail) return { ok: false };
      host.stored[account] = groups;
      return { ok: true, groups };
    }),
    tabMaster: vi.fn(async () => [
      { id: "t1", title: "Installed RPG", position: 1, filtersMode: "and", filters: [{ type: "installed", inverted: false, params: { installed: true } }] },
      { id: "AllGames", title: "All", position: 0 },
    ]),
  };
  return host;
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));
const rulesGroup = { name: "Installed", kind: "rules" as const, appIds: [], added: [], hidden: [], rules: { mode: "all" as const, rules: [{ type: "installed" as const, inverted: false, params: {} }] } };

afterEach(() => vi.useRealTimers());

describe("createGroupsClient", () => {
  it("saves a rule group for the current account and evaluates it", async () => {
    const host = memoryHost();
    const client = createGroupsClient(host, globals());
    const saved = await client.save(rulesGroup);
    expect(saved?.members).toEqual([10, 30]);
    expect(saved?.id).toMatch(/^grp:/);
    expect(host.write).toHaveBeenCalledWith("22202", expect.any(Array));
    expect(client.list().map((g) => g.name)).toEqual(["Installed"]);
    client.stop();
  });

  it("previews rules without saving", async () => {
    const client = createGroupsClient(memoryHost(), globals());
    await settle();
    expect(client.preview({ mode: "all", rules: [{ type: "tags", inverted: false, params: { ids: [122], match: "any" } }] })).toEqual([10]);
    expect(client.preview({ mode: "all", rules: [{ type: "installed", inverted: false, params: {} }] }, { hidden: [30], added: [20] })).toEqual([10, 20]);
    client.stop();
  });

  it("a failed write keeps what was there", async () => {
    const host = memoryHost();
    const client = createGroupsClient(host, globals());
    await client.save(rulesGroup);
    host.fail = true;
    expect(await client.save({ ...rulesGroup, name: "Other" })).toBeNull();
    expect(client.list().map((g) => g.name)).toEqual(["Installed"]);
    client.stop();
  });

  it("each Steam account has its own groups", async () => {
    const host = memoryHost({ "22202": [{ id: "grp:a", name: "Mine", kind: "manual", appIds: [10], added: [], hidden: [] }] });
    const steam = globals();
    const client = createGroupsClient(host, steam);
    await settle();
    expect(client.list().map((g) => g.id)).toEqual(["grp:a"]);
    steam.App = { m_CurrentUser: { strSteamID: "76561197960287931" } };
    await client.save({ ...rulesGroup, name: "Second" });
    expect(Object.keys(host.stored).sort()).toEqual(["22202", "22203"]);
    expect(client.list().map((g) => g.name)).toEqual(["Second"]);
    client.stop();
  });

  it("migrates a theme's hand-picked groups once", async () => {
    const host = memoryHost();
    const client = createGroupsClient(host, globals());
    const legacy = [{ id: "own:1", name: "Faves", appIds: [20, 10] }];
    await client.migrate(legacy);
    await client.migrate(legacy);
    expect(client.list()).toEqual([expect.objectContaining({ kind: "manual", name: "Faves", legacyId: "own:1", members: [20, 10] })]);
    expect(host.write).toHaveBeenCalledTimes(1);
    client.stop();
  });

  it("offers Tab Master tabs with their counts and imports them once", async () => {
    const host = memoryHost();
    const client = createGroupsClient(host, globals());
    expect(await client.importSources()).toEqual([{ id: "t1", name: "Installed RPG", count: 2, imported: false, unknown: [] }]);
    const imported = await client.import(["t1"]);
    expect(imported.map((g) => g.members)).toEqual([[10, 30]]);
    expect(await client.import(["t1"])).toEqual([]);
    expect((await client.importSources())[0].imported).toBe(true);
    client.stop();
  });

  it("tells subscribers when the library changes, and only while someone listens", async () => {
    vi.useFakeTimers();
    const steam = globals();
    const client = createGroupsClient(memoryHost({ "22202": [{ ...rulesGroup, id: "grp:i" }] }), steam);
    await vi.runOnlyPendingTimersAsync();
    const listener = vi.fn();
    const off = client.subscribe(listener);
    APPS[1].installed = true;
    (steam.collectionStore as { GetCollection: (id: string) => unknown }).GetCollection = (id: string) =>
      id === "type-games" ? { visibleApps: APPS } : id === "local-install" ? { allApps: APPS.filter((a) => a.installed) } : undefined;
    await vi.advanceTimersByTimeAsync(3000);
    expect(listener).toHaveBeenCalled();
    expect(client.list()[0].members).toEqual([10, 20, 30]);
    off();
    APPS[1].installed = false;
    expect(vi.getTimerCount()).toBe(0);
    client.stop();
  });

  it("catalog lists collections, tags with names and other groups", async () => {
    const client = createGroupsClient(memoryHost(), globals());
    await client.save(rulesGroup);
    const catalog = client.catalog("es");
    expect(catalog.collections).toEqual([{ id: "uc-1", name: "Mine" }]);
    expect(catalog.tags).toEqual([{ id: 122, name: "RPG" }]);
    expect(catalog.features.find((f) => f.id === 28)?.name).toBe("Compatibilidad total con mando");
    expect(catalog.groups.map((g) => g.name)).toEqual(["Installed"]);
    client.stop();
  });
});
