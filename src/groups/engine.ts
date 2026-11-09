import { GROUP_LIMITS, type AppFacts, type AppKind, type EvaluationContext, type GroupDefinition, type Rule, type RuleSet } from "./types";

const DAY = 86_400;
const GIB = 1024 ** 3;

/** True or false when the rule can be decided, null when the app lacks the data (matches neither way). */
type Verdict = boolean | null;

const isNumber = (item: unknown): item is number => typeof item === "number" && Number.isFinite(item);
const isString = (item: unknown): item is string => typeof item === "string";
const num = (value: unknown): number => (isNumber(value) ? value : 0);
const list = <T>(value: unknown, guard: (item: unknown) => item is T): T[] => (Array.isArray(value) ? value.filter(guard) : []);
const rulesOf = (set: RuleSet | undefined): Rule[] => (Array.isArray(set?.rules) ? set.rules : []);
const fold = (text: string) => text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();

function compare(value: number, op: unknown, target: number): Verdict {
  if (op === "more") return value > target;
  if (op === "less") return value < target;
  if (op === "atLeast") return value >= target;
  if (op === "atMost") return value <= target;
  return null;
}

function known(value: number, check: (value: number) => Verdict): Verdict {
  return value > 0 ? check(value) : null;
}

function dated(value: number, params: Record<string, unknown>, now: number): Verdict {
  if (params.op === "unknown") return value === 0;
  if (!value) return null;
  if (params.op === "before") return value < num(params.date);
  if (params.op === "after") return value > num(params.date);
  if (params.op === "within") return now - value <= num(params.days) * DAY;
  if (params.op === "olderThan") return now - value > num(params.days) * DAY;
  return null;
}

// Name patterns are compiled once, not once per app; an invalid one matches nothing.
const patterns = new Map<string, RegExp | null>();
function compiled(source: string): RegExp | null {
  if (!patterns.has(source)) {
    if (patterns.size > 200) patterns.clear();
    let pattern: RegExp | null = null;
    try { pattern = new RegExp(source, "i"); } catch { /* stays null */ }
    patterns.set(source, pattern);
  }
  return patterns.get(source) ?? null;
}

function matchSet<T>(wanted: readonly T[], have: readonly T[], match: unknown): Verdict {
  if (!wanted.length) return null;
  return match === "all" ? wanted.every((id) => have.includes(id)) : wanted.some((id) => have.includes(id));
}

interface Walk {
  ctx: EvaluationContext;
  depth: number;
  /** Groups being evaluated up the chain, so a group that refers back to itself matches nothing. */
  visiting: Set<string>;
  /** Members of the groups other rules refer to, worked out once per evaluation instead of once per app. */
  memo: Map<string, Set<number>>;
}

function decide(rule: Rule, app: AppFacts, walk: Walk): Verdict {
  const p = rule.params;
  const { ctx } = walk;
  switch (rule.type) {
    case "installed": return app.installed;
    case "collection": return typeof p.id === "string" ? app.collections.includes(p.id) : null;
    case "group": {
      const id = typeof p.id === "string" ? p.id : "";
      const definition = ctx.definition(id);
      if (!definition || walk.visiting.has(id)) return null;
      const key = `${id}|${[...walk.visiting].sort().join(",")}`;
      let found = walk.memo.get(key);
      if (!found) { found = new Set(members(definition, ctx, walk)); walk.memo.set(key, found); }
      return found.has(app.appId);
    }
    case "name": {
      if (typeof p.pattern === "string" && p.pattern) {
        const pattern = compiled(p.pattern);
        return pattern ? pattern.test(app.name) : null;
      }
      const text = typeof p.text === "string" ? fold(p.text.trim()) : "";
      return text ? fold(app.name).includes(text) : null;
    }
    case "kind": return list(p.kinds, isString).includes(app.kind);
    case "deckCompat":
    case "steamosCompat": {
      const level = rule.type === "deckCompat" ? app.deckCompat : app.steamosCompat;
      const levels = list(p.levels, isNumber);
      return level === 0 && !levels.includes(0) ? null : levels.includes(level);
    }
    case "tags": return matchSet(list(p.ids, isNumber), app.tags, p.match);
    case "features": return matchSet(list(p.ids, isNumber), app.features, p.match);
    case "playtime": return compare(app.playtimeMinutes, p.op, num(p.hours) * 60);
    case "lastPlayed":
      if (p.op === "never" || p.op === "unknown") return app.lastPlayed === 0;
      if (p.op === "before" || p.op === "after") return dated(app.lastPlayed, p, ctx.now);
      return known(app.lastPlayed, (value) => compare(ctx.now - value, p.op, num(p.days) * DAY));
    case "released": return dated(app.released, p, ctx.now);
    case "purchased": return dated(app.purchased, p, ctx.now);
    case "size": return known(app.sizeBytes, (value) => compare(value, p.op, num(p.gb) * GIB));
    case "review":
      return known(p.source === "metacritic" ? app.metacritic : app.reviewPercent, (value) => compare(value, p.op, num(p.value)));
    case "achievements":
      if (!app.achievementsTotal) return null;
      return compare(p.measure === "count" ? app.achievementsDone : app.achievementsPercent, p.op, num(p.value));
    case "friends": {
      const owners = ctx.friendOwners(app.appId);
      if (owners === null) return null;
      const ids = list(p.ids, isString);
      return ids.length ? matchSet(ids, owners, p.match) : owners.length > 0;
    }
    case "familyShared": return app.familyShared;
    case "demo": return app.demo;
    case "comingSoon": return app.comingSoon;
    case "streamable": return app.streamable;
    case "sdCard":
      if (p.card === "current") return app.sdCardCurrent;
      return typeof p.card === "string" && p.card ? app.sdCard === p.card : app.sdCard !== null;
    case "games": return list(p.ids, isNumber).includes(app.appId);
    case "installFolder": return app.installFolder === null || typeof p.folder !== "string" ? null : app.installFolder === p.folder;
    case "all":
      if (walk.depth >= GROUP_LIMITS.depth) return null;
      return matchesSet(p as unknown as RuleSet, app, { ...walk, depth: walk.depth + 1 });
    default: return null;
  }
}

function matches(rule: Rule, app: AppFacts, walk: Walk): boolean {
  const verdict = decide(rule, app, walk);
  return verdict === null ? false : verdict !== rule.inverted;
}

function matchesSet(set: RuleSet | undefined, app: AppFacts, walk: Walk): boolean {
  const rules = rulesOf(set);
  if (!rules.length) return false;
  return set?.mode === "any" ? rules.some((rule) => matches(rule, app, walk)) : rules.every((rule) => matches(rule, app, walk));
}

/** Kinds a rule set asks for by name: only those reach apps outside the default universe. */
function namedKinds(set: RuleSet | undefined, into = new Set<AppKind>()): Set<AppKind> {
  for (const rule of rulesOf(set)) {
    if (rule.type === "kind" && !rule.inverted) list(rule.params.kinds, isString).forEach((kind) => into.add(kind as AppKind));
    if (rule.type === "all") namedKinds(rule.params as unknown as RuleSet, into);
  }
  return into;
}

function members(group: GroupDefinition, ctx: EvaluationContext, walk: Walk): number[] {
  const hidden = new Set(group.hidden);
  if (group.kind === "manual") return group.appIds.filter((id) => !hidden.has(id) && ctx.facts(id) !== undefined);
  const inner: Walk = { ctx, depth: 0, visiting: new Set([...walk.visiting, group.id]), memo: walk.memo };
  const kinds = namedKinds(group.rules);
  for (const kind of group.include ?? []) kinds.add(kind);
  const candidates = [...ctx.universe, ...(ctx.extended ?? []).filter((id) => {
    const kind = ctx.facts(id)?.kind;
    return kind !== undefined && kinds.has(kind);
  })];
  const added = new Set(group.added);
  const result: number[] = [];
  for (const id of candidates) {
    const app = ctx.facts(id);
    if (!app || hidden.has(id)) continue;
    if (added.has(id) || matchesSet(group.rules, app, inner)) result.push(id);
  }
  const seen = new Set(result);
  for (const id of group.added) if (!seen.has(id) && !hidden.has(id) && ctx.facts(id)) result.push(id);
  return result;
}

/** The games in a group, in the universe's order; a manual group keeps the order its games were picked in. */
export function evaluateGroup(group: GroupDefinition, ctx: EvaluationContext): number[] {
  return members(group, ctx, { ctx, depth: 0, visiting: new Set(), memo: new Map() });
}
