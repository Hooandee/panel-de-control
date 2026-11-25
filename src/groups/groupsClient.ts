import { buildCatalog, type RuleCatalog } from "./catalog";
import { evaluateGroup } from "./engine";
import { normalizeGroup, normalizeGroups } from "./normalize";
import { createFriendOwnership, readSteam, steamAccount, type SteamGlobals, type SteamSnapshot } from "./steamFacts";
import { translateTabMasterTab, type ImportedTab } from "./tabMasterImport";
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
const MIGRATED_KEY = "pdc.groups.migrated.";

/** Which legacy groups were already moved, per account (kept in the Steam UI's own storage). */
function localMigrated(): { read(account: string): string[]; write(account: string, ids: readonly string[]): void } {
  const store = () => { try { return globalThis.localStorage ?? null; } catch { return null; } };
  return {
    read(account) {
      try {
        const value: unknown = JSON.parse(store()?.getItem(MIGRATED_KEY + account) ?? "[]");
        return Array.isArray(value) ? value.filter((id): id is string => typeof id === "string") : [];
      } catch { return []; }
    },
    write(account, ids) { try { store()?.setItem(MIGRATED_KEY + account, JSON.stringify([...new Set(ids)].slice(-500))); } catch { /* best effort */ } },
  };
}

function usesFriends(rules: readonly Rule[] | undefined): boolean {
  return (rules ?? []).some((rule) => rule.type === "friends" || (rule.type === "all" && usesFriends((rule.params as unknown as RuleSet).rules)));
}

export function createGroupsClient(host: GroupsHost, globals: SteamGlobals, options: { now?: () => number; doc?: Document; migrated?: ReturnType<typeof localMigrated> } = {}): GroupsClient {
  const now = options.now ?? (() => Date.now());
  const migrated = options.migrated ?? localMigrated();
  const listeners = new Set<() => void>();
  let account: string | null = null;
  let definitions: GroupDefinition[] = [];
  let loading: Promise<void> | null = null;
  let snapshot: SteamSnapshot | null = null;
  let groups: ThemeGroup[] = [];
  let timer: ReturnType<typeof setInterval> | null = null;
  let loaded = false;
  let checkedBucket = 0;
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
  // A Steam store that throws while loading keeps the last good result instead of breaking every theme.
  const recompute = () => {
    try {
      snapshot = readSteam(globals);
      const ctx = context(snapshot, definitions);
      // Frozen once here: every theme gets the same objects and none can change them for the others.
      groups = Object.freeze(definitions.map((group) => Object.freeze({ ...group, members: Object.freeze(evaluateGroup(group, ctx)) }))) as ThemeGroup[];
    } catch { /* next check tries again */ }
  };
  const load = (): Promise<void> => {
    const current = steamAccount(globals);
    if (current === account && loading) return loading;
    if (current !== account) { definitions = []; groups = []; friends.reset(); }
    account = current;
    loaded = false;
    const attempt: Promise<void> = (current ? host.read(current) : Promise.resolve([]))
      .then((value) => { if (account === current) { definitions = normalizeGroups(value); loaded = true; } })
      // Not loaded: nothing may be written until a read succeeds, or a save would replace the stored groups.
      .catch(() => { if (loading === attempt) loading = null; })
      .finally(() => { if (account === current) { recompute(); notify(); } });
    loading = attempt;
    return attempt;
  };
  const check = () => {
    if (options.doc?.hidden) return;
    if (steamAccount(globals) !== account || !loading) { void load(); return; }
    // Date rules ("played in the last week") move with the clock too, so look again every ten minutes regardless.
    const bucket = Math.floor(now() / 600_000);
    let signature: string;
    try { signature = readSteam(globals).signature; } catch { return; }
    if (signature !== snapshot?.signature || bucket !== checkedBucket) { checkedBucket = bucket; recompute(); notify(); }
  };
  // Every change is computed from the stored groups at the moment it is written, one at a time, and only for the
  // account the caller started with: a failed read, an account switch or two saves at once never lose groups.
  const mutate = (expected: string | null, change: (current: readonly GroupDefinition[]) => GroupDefinition[] | null): Promise<boolean> => {
    const run = writes.catch(() => undefined).then(async () => {
      await load();
      const target = account;
      if (!target || !loaded || target !== expected) return false;
      const next = change(definitions);
      if (!next) return false;
      const reply = await host.write(target, next).catch(() => undefined);
      if (!reply?.ok || account !== target) return false;
      definitions = normalizeGroups(reply.groups ?? next);
      recompute(); notify();
      return true;
    });
    writes = run;
    return run;
  };
  const room = (current: readonly GroupDefinition[]) => Math.max(0, GROUP_LIMITS.groups - current.length);
  const isImported = (current: readonly GroupDefinition[], group: GroupDefinition) => current.some((item) => item.importedFrom === group.importedFrom);
  const tabMasterTabs = async (target: string): Promise<ImportedTab[]> => {
    const tabs = await host.tabMaster(target).catch(() => []);
    return (Array.isArray(tabs) ? tabs : []).flatMap((tab) => translateTabMasterTab(tab as Record<string, unknown>) ?? []);
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
      const saved = await mutate(account, (current) => {
        const exists = current.some((item) => item.id === group.id);
        if (!exists && current.length >= GROUP_LIMITS.groups) return null;
        return exists ? current.map((item) => (item.id === group.id ? group : item)) : [...current, group];
      });
      return saved ? groups.find((item) => item.id === group.id) ?? null : null;
    },
    async remove(id) {
      await load();
      return mutate(account, (current) => (current.some((group) => group.id === id) ? current.filter((group) => group.id !== id) : null));
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
      return (await tabMasterTabs(account)).map(({ tabId, group, unknown }) => ({
        id: tabId,
        name: group.name,
        count: group.rules ? preview(group.rules, group).length : 0,
        imported: isImported(definitions, group),
        unknown,
      }));
    },
    async import(ids) {
      await load();
      const expected = account;
      if (!expected) return [];
      const wanted = new Set(ids);
      const tabs = (await tabMasterTabs(expected)).filter((item) => wanted.has(item.tabId));
      let fresh: GroupDefinition[] = [];
      const saved = await mutate(expected, (current) => {
        fresh = tabs
          .filter((item) => !isImported(current, item.group))
          .map(({ group }) => ({ ...group, id: current.some((item) => item.id === group.id) ? newId() : group.id }))
          .slice(0, room(current));
        return fresh.length ? [...current, ...fresh] : null;
      });
      return saved ? groups.filter((group) => fresh.some((item) => item.id === group.id)) : [];
    },
    async migrate(legacy) {
      await load();
      const expected = account;
      if (!expected) return;
      // A legacy group moves once per account: deleting the moved group never brings it back.
      const done = new Set(migrated.read(expected));
      let moved: GroupDefinition[] = [];
      const saved = await mutate(expected, (current) => {
        moved = legacy
          .filter((old) => !done.has(old.id) && !current.some((group) => group.legacyId === old.id))
          .flatMap((old) => {
            const group = normalizeGroup({ id: newId() + old.id.replace(/[^A-Za-z0-9]/g, "").slice(-8), name: old.name, kind: "manual", appIds: [...old.appIds], added: [], hidden: [], legacyId: old.id });
            return group ? [group] : [];
          })
          .slice(0, room(current));
        return moved.length ? [...current, ...moved] : null;
      });
      const already = legacy.filter((old) => definitions.some((group) => group.legacyId === old.id)).map((old) => old.id);
      if (saved || already.length) migrated.write(expected, [...done, ...moved.map((group) => group.legacyId!), ...already]);
    },
    status: () => ({ friends: friends.loading() ? "loading" : friendsAsked ? "ready" : "idle" }),
    stop() {
      friends.stop();
      listeners.clear();
      if (timer) clearInterval(timer);
      timer = null;
    },
  };
}
