import { buildCatalog, type RuleCatalog } from "./catalog";
import { evaluateGroup } from "./engine";
import { normalizeGroup, normalizeGroups } from "./normalize";
import { createFriendOwnership, readSteam, steamAccount, type SteamGlobals, type SteamSnapshot } from "./steamFacts";
import { translateTabMasterTab } from "./tabMasterImport";
import { GROUP_LIMITS, type EvaluationContext, type GroupDefinition, type Rule, type RuleSet } from "./types";

export type ThemeGroup = GroupDefinition & { members: number[] };
export interface ImportSource { id: string; name: string; count: number; imported: boolean; unknown: string[] }

/** What every theme gets as `context.groups`: Panel keeps, evaluates and shares the groups; themes only show them. */
export interface ThemeGroupsAccess {
  list(): readonly ThemeGroup[];
  subscribe(listener: () => void): () => void;
  /** Creates the group when its id is empty. Resolves null when it could not be saved. */
  save(group: Omit<GroupDefinition, "id"> & { id?: string }): Promise<ThemeGroup | null>;
  remove(id: string): Promise<boolean>;
  /** The games a rule set would hold right now, for a live count while the user edits it. */
  preview(rules: RuleSet, extra?: Partial<Pick<GroupDefinition, "added" | "hidden" | "include">>): number[];
  catalog(language?: string): RuleCatalog;
  importSources(): Promise<ImportSource[]>;
  import(ids: readonly string[]): Promise<ThemeGroup[]>;
  /** Moves a theme's own hand-picked groups here once; running it again changes nothing. */
  migrate(legacy: readonly { id: string; name: string; appIds: readonly number[] }[]): Promise<void>;
  /** What is still loading, so an editor can say so instead of showing a count that will change. */
  status(): { friends: "idle" | "loading" | "ready" };
}

export interface GroupsHost {
  read(account: string): Promise<unknown>;
  write(account: string, groups: GroupDefinition[]): Promise<{ ok?: boolean; groups?: unknown } | undefined>;
  tabMaster(account: string): Promise<unknown>;
}

export interface GroupsClient extends ThemeGroupsAccess {
  stop(): void;
}

const CHECK_MS = 3000;

function usesFriends(rules: readonly Rule[] | undefined): boolean {
  return (rules ?? []).some((rule) => rule.type === "friends" || (rule.type === "all" && usesFriends((rule.params as unknown as RuleSet).rules)));
}

export function createGroupsClient(host: GroupsHost, globals: SteamGlobals, options: { now?: () => number; doc?: Document } = {}): GroupsClient {
  const now = options.now ?? (() => Date.now());
  const listeners = new Set<() => void>();
  let account: string | null = null;
  let definitions: GroupDefinition[] = [];
  let loading: Promise<void> | null = null;
  let snapshot: SteamSnapshot | null = null;
  let groups: ThemeGroup[] = [];
  let timer: ReturnType<typeof setInterval> | null = null;
  let writes: Promise<unknown> = Promise.resolve();
  let friendsAsked = false;
  const friends = createFriendOwnership(globals, () => {
    friendsAsked = true;
    if (!friends.loading() && definitions.some((group) => usesFriends(group.rules?.rules))) recompute();
    notify();
  }, now);

  const notify = () => listeners.forEach((listener) => { try { listener(); } catch { /* one theme never breaks another */ } });
  const context = (steam: SteamSnapshot, defs: readonly GroupDefinition[]): EvaluationContext => ({
    facts: steam.facts,
    universe: steam.universe,
    extended: steam.extended,
    friendOwners: (appId) => friends.owners(appId),
    definition: (id) => defs.find((group) => group.id === id),
    now: Math.floor(now() / 1000),
  });
  const recompute = () => {
    snapshot = readSteam(globals);
    const ctx = context(snapshot, definitions);
    groups = definitions.map((group) => ({ ...group, members: evaluateGroup(group, ctx) }));
  };
  const load = (): Promise<void> => {
    const current = steamAccount(globals);
    if (current === account && loading) return loading;
    account = current;
    definitions = []; groups = [];
    loading = (current ? host.read(current) : Promise.resolve([]))
      .then((value) => { if (account === current) definitions = normalizeGroups(value); })
      .catch(() => { /* keep what we have; a later look tries again */ loading = null; })
      .finally(() => { if (account === current) { recompute(); notify(); } });
    return loading;
  };
  const check = () => {
    if (options.doc?.hidden) return;
    if (steamAccount(globals) !== account) { void load(); return; }
    const next = readSteam(globals);
    if (next.signature !== snapshot?.signature) { recompute(); notify(); }
  };
  const persist = async (next: GroupDefinition[]): Promise<boolean> => {
    await load();
    const target = account;
    if (!target) return false;
    const run = writes.catch(() => undefined).then(() => host.write(target, next));
    writes = run;
    const reply = await run.catch(() => undefined);
    if (!reply?.ok || account !== target) return false;
    definitions = normalizeGroups(reply.groups ?? next);
    recompute(); notify();
    return true;
  };
  const newId = () => `grp:${now().toString(36)}${Math.floor(Math.random() * 36 ** 4).toString(36)}`;

  const preview: ThemeGroupsAccess["preview"] = (rules, extra = {}) => {
    const steam = snapshot ?? readSteam(globals);
    const group = normalizeGroup({ id: "preview", name: "preview", kind: "rules", appIds: [], added: extra.added ?? [], hidden: extra.hidden ?? [], include: extra.include, rules });
    return group ? evaluateGroup(group, context(steam, definitions)) : [];
  };

  void load();

  return {
    list: () => groups,
    subscribe(listener) {
      listeners.add(listener);
      if (!timer) timer = setInterval(check, CHECK_MS);
      return () => {
        listeners.delete(listener);
        if (!listeners.size && timer) { clearInterval(timer); timer = null; }
      };
    },
    async save(input) {
      await load();
      const group = normalizeGroup({ ...input, id: input.id || newId() });
      if (!group) return null;
      const exists = definitions.some((item) => item.id === group.id);
      if (!exists && definitions.length >= GROUP_LIMITS.groups) return null;
      const next = exists ? definitions.map((item) => (item.id === group.id ? group : item)) : [...definitions, group];
      return (await persist(next)) ? groups.find((item) => item.id === group.id) ?? null : null;
    },
    async remove(id) {
      await load();
      if (!definitions.some((group) => group.id === id)) return false;
      return persist(definitions.filter((group) => group.id !== id));
    },
    preview,
    catalog(language = "es") {
      const tags = new Set<number>();
      const steam = snapshot ?? readSteam(globals);
      for (const id of steam.universe) steam.facts(id)?.tags.forEach((tag) => tags.add(tag));
      return buildCatalog(globals, friends, definitions, language, tags);
    },
    async importSources() {
      await load();
      if (!account) return [];
      const tabs = await host.tabMaster(account).catch(() => []);
      return (Array.isArray(tabs) ? tabs : []).flatMap((tab) => {
        const imported = translateTabMasterTab(tab as Record<string, unknown>);
        if (!imported) return [];
        const { group } = imported;
        return [{
          id: imported.tabId,
          name: group.name,
          count: group.rules ? preview(group.rules, group).length : 0,
          imported: definitions.some((item) => item.importedFrom === group.importedFrom),
          unknown: imported.unknown,
        }];
      });
    },
    async import(ids) {
      await load();
      if (!account) return [];
      const wanted = new Set(ids);
      const tabs = await host.tabMaster(account).catch(() => []);
      const fresh = (Array.isArray(tabs) ? tabs : [])
        .map((tab) => translateTabMasterTab(tab as Record<string, unknown>))
        .filter((item): item is NonNullable<typeof item> => !!item && wanted.has(item.tabId))
        .map((item) => item.group)
        .filter((group) => !definitions.some((item) => item.importedFrom === group.importedFrom))
        .map((group) => ({ ...group, id: definitions.some((item) => item.id === group.id) ? newId() : group.id }))
        .slice(0, Math.max(0, GROUP_LIMITS.groups - definitions.length));
      if (!fresh.length || !(await persist([...definitions, ...fresh]))) return [];
      return groups.filter((group) => fresh.some((item) => item.id === group.id));
    },
    async migrate(legacy) {
      await load();
      if (!account) return;
      const missing = legacy.filter((old) => !definitions.some((group) => group.legacyId === old.id));
      if (!missing.length) return;
      const moved = missing.flatMap((old) => {
        const group = normalizeGroup({ id: newId() + old.id.replace(/[^A-Za-z0-9]/g, "").slice(-8), name: old.name, kind: "manual", appIds: [...old.appIds], added: [], hidden: [], legacyId: old.id });
        return group ? [group] : [];
      }).slice(0, Math.max(0, GROUP_LIMITS.groups - definitions.length));
      if (moved.length) await persist([...definitions, ...moved]);
    },
    status: () => ({ friends: friends.loading() ? "loading" : friendsAsked ? "ready" : "idle" }),
    stop() {
      listeners.clear();
      if (timer) clearInterval(timer);
      timer = null;
    },
  };
}
