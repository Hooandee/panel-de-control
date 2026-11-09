import { GROUP_LIMITS, RULE_TYPES, type GroupDefinition, type Rule, type RuleSet } from "./types";

// Mirrored by py_modules/theme_groups.py: both sides accept and drop the same records.
export const GROUP_ID = /^[A-Za-z0-9:_-]{1,64}$/;
const TAG = /^[\x20-\x7E]{1,80}$/;
const RULE_TYPE_SET = new Set<string>(RULE_TYPES);
const MAX_PARAMS_BYTES = 4096;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

function appIds(value: unknown, limit: number): number[] | null {
  if (!Array.isArray(value)) return null;
  const ids = value.filter((id): id is number => Number.isInteger(id) && id > 0 && id < 2 ** 32);
  return [...new Set(ids)].slice(0, limit);
}

function plainParams(value: unknown): Record<string, unknown> | null {
  if (!isRecord(value)) return null;
  try {
    const text = JSON.stringify(value);
    return text.length <= MAX_PARAMS_BYTES ? (JSON.parse(text) as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

function normalizeRule(value: unknown, depth: number): Rule | null {
  if (!isRecord(value) || typeof value.type !== "string" || !RULE_TYPE_SET.has(value.type) || typeof value.inverted !== "boolean") return null;
  if (value.type === "all") {
    if (depth >= GROUP_LIMITS.depth) return null;
    const nested = normalizeRuleSet(value.params, depth + 1);
    return nested ? { type: "all", inverted: value.inverted, params: { ...nested } } : null;
  }
  const params = plainParams(value.params);
  return params ? { type: value.type as Rule["type"], inverted: value.inverted, params } : null;
}

export function normalizeRuleSet(value: unknown, depth = 0): RuleSet | null {
  if (!isRecord(value) || (value.mode !== "all" && value.mode !== "any") || !Array.isArray(value.rules)) return null;
  const rules = value.rules.slice(0, GROUP_LIMITS.rulesPerLevel).map((rule) => normalizeRule(rule, depth)).filter((rule): rule is Rule => rule !== null);
  return { mode: value.mode, rules };
}

export function normalizeGroup(value: unknown): GroupDefinition | null {
  if (!isRecord(value) || typeof value.id !== "string" || !GROUP_ID.test(value.id) || typeof value.name !== "string") return null;
  const name = value.name.trim().slice(0, GROUP_LIMITS.name);
  if (!name || (value.kind !== "manual" && value.kind !== "rules")) return null;
  const picked = appIds(value.appIds, GROUP_LIMITS.manualGames);
  const added = appIds(value.added ?? [], GROUP_LIMITS.manualGames);
  const hidden = appIds(value.hidden ?? [], GROUP_LIMITS.manualGames);
  if (!picked || !added || !hidden) return null;
  const group: GroupDefinition = { id: value.id, name, kind: value.kind, appIds: value.kind === "manual" ? picked : [], added, hidden };
  if (value.kind === "rules") {
    const rules = normalizeRuleSet(value.rules);
    if (!rules) return null;
    group.rules = rules;
  }
  const include = Array.isArray(value.include) ? [...new Set(value.include.filter((kind): kind is NonNullable<GroupDefinition["include"]>[number] =>
    kind === "software" || kind === "music" || kind === "tool" || kind === "video" || kind === "other"))] : [];
  if (value.kind === "rules" && include.length) group.include = include;
  if (typeof value.importedFrom === "string" && TAG.test(value.importedFrom)) group.importedFrom = value.importedFrom;
  if (typeof value.legacyId === "string" && TAG.test(value.legacyId)) group.legacyId = value.legacyId;
  return group;
}

/** Valid groups in order, duplicates and anything past the limit dropped; one bad record never costs the rest. */
export function normalizeGroups(value: unknown): GroupDefinition[] {
  if (!Array.isArray(value)) return [];
  const seen = new Set<string>();
  const out: GroupDefinition[] = [];
  for (const item of value) {
    const group = normalizeGroup(item);
    if (!group || seen.has(group.id)) continue;
    seen.add(group.id);
    out.push(group);
    if (out.length >= GROUP_LIMITS.groups) break;
  }
  return out;
}
