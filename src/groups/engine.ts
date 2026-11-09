import { GROUP_LIMITS, type AppFacts, type AppKind, type EvaluationContext, type GroupDefinition, type Rule, type RuleSet } from "./types";

const DAY = 86_400;
const GB = 1e9;

/** True or false when the rule can be decided, null when the app lacks the data (matches neither way). */
type Verdict = boolean | null;

const num = (value: unknown, fallback = 0): number => (typeof value === "number" && Number.isFinite(value) ? value : fallback);
const list = <T>(value: unknown, guard: (item: unknown) => item is T): T[] => (Array.isArray(value) ? value.filter(guard) : []);
const isNumber = (item: unknown): item is number => typeof item === "number" && Number.isFinite(item);
const isString = (item: unknown): item is string => typeof item === "string";
const fold = (text: string) => text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();

function compare(value: number, op: unknown, target: number): Verdict {
  if (op === "more") return value > target;
  if (op === "less") return value < target;
  return null;
}

function known(value: number, check: (value: number) => Verdict): Verdict {
  return value > 0 ? check(value) : null;
}

function dated(value: number, params: Record<string, unknown>, now: number): Verdict {
  if (!value) return null;
  if (params.op === "before") return value < num(params.date);
  if (params.op === "after") return value > num(params.date);
  if (params.op === "within") return now - value <= num(params.days) * DAY;
  return null;
}

function matchSet(wanted: number[], have: number[], match: unknown): Verdict {
  if (!wanted.length) return null;
  return match === "all" ? wanted.every((id) => have.includes(id)) : wanted.some((id) => have.includes(id));
}

interface Walk {
  ctx: EvaluationContext;
  depth: number;
  /** Groups being evaluated up the chain, so a group that refers back to itself matches nothing. */
  visiting: Set<string>;
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
      return members(definition, ctx, walk).includes(app.appId);
    }
    case "name": {
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
      if (p.op === "never") return app.lastPlayed === 0;
      return known(app.lastPlayed, (value) => compare(ctx.now - value, p.op, num(p.days) * DAY));
    case "released": return dated(app.released, p, ctx.now);
    case "purchased": return dated(app.purchased, p, ctx.now);
    case "size": return known(app.sizeBytes, (value) => compare(value, p.op, num(p.gb) * GB));
    case "review":
      return known(p.source === "metacritic" ? app.metacritic : app.reviewPercent, (value) => compare(value, p.op, num(p.value)));
    case "achievements":
      if (!app.achievementsTotal) return null;
      return compare(p.measure === "count" ? app.achievementsDone : app.achievementsPercent, p.op, num(p.value));
    case "friends": {
      const owners = ctx.friendOwners(app.appId);
      if (owners === null) return null;
      const ids = list(p.ids, isString);
      if (!ids.length) return owners.length > 0;
      return p.match === "all" ? ids.every((id) => owners.includes(id)) : ids.some((id) => owners.includes(id));
    }
    case "familyShared": return app.familyShared;
    case "demo": return app.demo;
    case "comingSoon": return app.comingSoon;
    case "streamable": return app.streamable;
    case "sdCard": return typeof p.card === "string" && p.card ? app.sdCard === p.card : app.sdCard !== null;
    case "installFolder": return app.installFolder === null || typeof p.folder !== "string" ? null : app.installFolder === p.folder;
    case "all": {
      if (walk.depth >= GROUP_LIMITS.depth) return null;
      return matchesSet(p as unknown as RuleSet, app, { ...walk, depth: walk.depth + 1 });
    }
    default: return null;
  }
}

function matches(rule: Rule, app: AppFacts, walk: Walk): boolean {
  const verdict = decide(rule, app, walk);
  return verdict === null ? false : verdict !== rule.inverted;
}

function matchesSet(set: RuleSet | undefined, app: AppFacts, walk: Walk): boolean {
  const rules = Array.isArray(set?.rules) ? set.rules : [];
  if (!rules.length) return false;
  return set?.mode === "any" ? rules.some((rule) => matches(rule, app, walk)) : rules.every((rule) => matches(rule, app, walk));
}

/** Kinds a rule set asks for by name: only those reach apps outside the default universe. */
function namedKinds(set: RuleSet | undefined, into = new Set<AppKind>()): Set<AppKind> {
  for (const rule of Array.isArray(set?.rules) ? set.rules : []) {
    if (rule.type === "kind" && !rule.inverted) list(rule.params.kinds, isString).forEach((kind) => into.add(kind as AppKind));
    if (rule.type === "all") namedKinds(rule.params as unknown as RuleSet, into);
  }
  return into;
}

function members(group: GroupDefinition, ctx: EvaluationContext, walk: Walk): number[] {
  const hidden = new Set(group.hidden);
  if (group.kind === "manual") return group.appIds.filter((id) => !hidden.has(id) && ctx.facts(id) !== undefined);
  const inner: Walk = { ctx, depth: 0, visiting: new Set([...walk.visiting, group.id]) };
  const kinds = namedKinds(group.rules);
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
  return members(group, ctx, { ctx, depth: 0, visiting: new Set() });
}
