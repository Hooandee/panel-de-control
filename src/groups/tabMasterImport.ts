import { isRecord, normalizeGroup } from "./normalize";
import type { GroupDefinition, Rule, RuleSet } from "./types";

// Tab Master tabs as groups. The translation only goes one way: once imported, a group belongs to Panel.

type Tab = Record<string, unknown>;
type Filter = { type?: unknown; inverted?: unknown; params?: unknown };

const BITS = { software: 2, music: 8192 } as const;
const record = (value: unknown): Record<string, unknown> => (isRecord(value) ? value : {});
const numbers = (value: unknown) => (Array.isArray(value) ? value.filter((n): n is number => typeof n === "number" && Number.isFinite(n)) : []);
const atOp = (condition: unknown) => (condition === "below" ? "atMost" : "atLeast");
const match = (mode: unknown) => (mode === "and" ? "all" : "any");

/** A Tab Master date (`{year, month?, day?}`) as the Unix second it starts or, for "below", the one after it ends. */
function dateBound(value: unknown, end: boolean): number | null {
  const { year, month, day } = record(value) as { year?: number; month?: number; day?: number };
  if (typeof year !== "number") return null;
  const date = !end ? new Date(year, (month ?? 1) - 1, day ?? 1)
    : day !== undefined ? new Date(year, (month ?? 1) - 1, day + 1)
      : month !== undefined ? new Date(year, month, 1) : new Date(year + 1, 0, 1);
  return Math.floor(date.getTime() / 1000);
}

function dateRule(type: "released" | "purchased" | "lastPlayed", p: Record<string, unknown>): Rule["params"] | null {
  if (p.isUnknown) return { op: "unknown" };
  if (p.date) {
    const date = dateBound(p.date, p.condition === "below");
    return date === null ? null : { op: p.condition === "below" ? "before" : "after", date };
  }
  if (typeof p.daysAgo === "number") {
    if (type === "lastPlayed") return { op: p.condition === "below" ? "more" : "less", days: p.daysAgo };
    return { op: p.condition === "below" ? "olderThan" : "within", days: p.daysAgo };
  }
  return null;
}

/** One filter as one rule, or null with the filter's type noted in `unknown`. */
function translate(filter: Filter, depth: number, unknown: string[]): Rule | null {
  const type = typeof filter.type === "string" ? filter.type : "";
  const p = record(filter.params);
  const inverted = filter.inverted === true;
  const rule = (ruleType: Rule["type"], params: Rule["params"] = {}, flip = false): Rule =>
    ({ type: ruleType, inverted: inverted !== flip, params });
  switch (type) {
    case "collection": return typeof p.id === "string" ? rule("collection", { id: p.id }) : null;
    case "installed": return rule("installed", {}, p.installed === false);
    case "regex": return typeof p.regex === "string" ? rule("name", { pattern: p.regex }) : null;
    // Tab Master keeps friends as Steam ids; ours are the 32-bit account ids Steam's friend store uses.
    case "friends": return rule("friends", { ids: numbers(p.friends).map((id) => String(id % 2 ** 32)), match: match(p.mode) });
    case "tags": return rule("tags", { ids: numbers(p.tags), match: match(p.mode) });
    case "whitelist": return rule("games", { ids: numbers(p.games) });
    case "blacklist": return rule("games", { ids: numbers(p.games) }, true);
    case "merge":
      if (depth >= 2) break;
      return rule("all", { ...translateSet(p.filters, p.mode, depth + 1, unknown) });
    case "platform": return rule("kind", { kinds: ["shortcut"] }, p.platform === "steam");
    case "deck compatibility": return rule("deckCompat", { levels: numbers([p.category]) });
    case "steamos compatibility": return rule("steamosCompat", { levels: numbers([p.category]) });
    case "review score":
      return rule("review", { source: p.type === "metacritic" ? "metacritic" : "steam", op: atOp(p.condition), value: Number(p.scoreThreshold) || 0 });
    case "time played": {
      const per = p.units === "minutes" ? 1 / 60 : p.units === "days" ? 24 : 1;
      return rule("playtime", { op: atOp(p.condition), hours: (Number(p.timeThreshold) || 0) * per });
    }
    case "size on disk": return rule("size", { op: atOp(p.condition), gb: Number(p.gbThreshold) || 0 });
    case "release date":
    case "purchase date":
    case "last played": {
      const target = type === "release date" ? "released" : type === "purchase date" ? "purchased" : "lastPlayed";
      const params = dateRule(target, p);
      return params ? rule(target, params) : null;
    }
    case "family sharing": return rule("familyShared", {}, p.isFamilyShared === false);
    case "demo": return rule("demo", {}, p.isDemo === false);
    case "coming soon": return rule("comingSoon", {}, p.isComingSoon === false);
    case "streamable": return rule("streamable", {}, p.isStreamable === false);
    case "steam features": return rule("features", { ids: numbers(p.features), match: match(p.mode) });
    case "achievements":
      return rule("achievements", { measure: p.thresholdType === "count" ? "count" : "percent", op: atOp(p.condition), value: Number(p.threshold) || 0 });
    case "sd card": {
      const card = p.card === 1 ? "" : typeof p.card === "string" ? p.card : "current";
      return rule("sdCard", card ? { card } : {});
    }
    case "install folder": return typeof p.driveName === "string" ? rule("installFolder", { folder: p.driveName }) : null;
  }
  unknown.push(type || "?");
  return null;
}

function translateSet(filters: unknown, mode: unknown, depth: number, unknown: string[]): RuleSet {
  const rules = (Array.isArray(filters) ? filters : []).map((filter) => translate(record(filter), depth, unknown)).filter((rule): rule is Rule => rule !== null);
  return { mode: mode === "or" ? "any" : "all", rules };
}

export interface ImportedTab { tabId: string; group: GroupDefinition; unknown: string[] }

/** A tab with filters as a rule group; Steam's own tabs (no filters) are left out. */
export function translateTabMasterTab(tab: Tab): ImportedTab | null {
  const tabId = typeof tab.id === "string" ? tab.id : "";
  if (!tabId || !Array.isArray(tab.filters) || !tab.filters.length) return null;
  const unknown: string[] = [];
  const set = translateSet(tab.filters, tab.filtersMode, 0, unknown);
  const added: number[] = [];
  const hidden: number[] = [];
  // At the top, "any filter" plus a list of games is "always include these"; "every filter" plus an excluded list is
  // "never these". Those read better as the group's own lists than as rules.
  set.rules = set.rules.filter((rule) => {
    if (rule.type !== "games") return true;
    const ids = numbers(rule.params.ids);
    if (set.mode === "any" && !rule.inverted) { added.push(...ids); return false; }
    if (set.mode === "all" && rule.inverted) { hidden.push(...ids); return false; }
    return true;
  });
  const bits = typeof tab.categoriesToInclude === "number" ? tab.categoriesToInclude : 1;
  const include = (Object.keys(BITS) as (keyof typeof BITS)[]).filter((kind) => bits & BITS[kind]);
  const group = normalizeGroup({
    id: `grp:tm-${tabId.replace(/[^A-Za-z0-9_-]/g, "").slice(0, 40) || "tab"}`,
    name: typeof tab.title === "string" && tab.title.trim() ? tab.title : "Tab Master",
    kind: "rules", appIds: [], added, hidden, rules: set, include,
    importedFrom: `tabmaster:${tabId}`.slice(0, 80),
  });
  return group ? { tabId, group, unknown } : null;
}
