import { describe, expect, it } from "vitest";

import { evaluateGroup } from "./engine";
import type { AppFacts, EvaluationContext, GroupDefinition, Rule } from "./types";

const DAY = 86_400;
const NOW = 2_000_000_000;

function app(appId: number, over: Partial<AppFacts> = {}): AppFacts {
  return {
    appId, name: `Game ${appId}`, kind: "game", installed: false, collections: [], tags: [], features: [],
    playtimeMinutes: 0, lastPlayed: 0, released: 0, purchased: 0, sizeBytes: 0, deckCompat: 0, steamosCompat: 0,
    metacritic: 0, reviewPercent: 0, achievementsPercent: 0, achievementsDone: 0, achievementsTotal: 0, familyShared: false, demo: false,
    comingSoon: false, streamable: false, installFolder: null, sdCard: null, sdCardCurrent: false, ...over,
  };
}

const APPS = [
  app(1, { name: "Hades", installed: true, collections: ["favorite"], tags: [122, 3959], features: [28], playtimeMinutes: 600,
    lastPlayed: NOW - 2 * DAY, released: NOW - 900 * DAY, purchased: NOW - 400 * DAY, sizeBytes: 15e9, deckCompat: 3,
    steamosCompat: 3, metacritic: 93, reviewPercent: 98, achievementsPercent: 80, achievementsDone: 40, achievementsTotal: 50, streamable: true,
    installFolder: "0", sdCard: null }),
  app(2, { name: "Dead Cells", installed: false, tags: [3959], playtimeMinutes: 30, lastPlayed: NOW - 60 * DAY,
    released: NOW - 10 * DAY, sizeBytes: 1e9, deckCompat: 2, metacritic: 89, reviewPercent: 90, achievementsPercent: 10,
    achievementsDone: 3, achievementsTotal: 30, familyShared: true }),
  app(3, { name: "Emulator", kind: "shortcut", installed: true, sdCard: "card-a", sdCardCurrent: true, installFolder: "1" }),
  app(4, { name: "Demo Thing", demo: true, comingSoon: true, deckCompat: 1 }),
  app(5, { name: "Soundtrack", kind: "music", installed: true }),
];

function ctx(definitions: GroupDefinition[] = [], owners: Record<number, string[] | null> = {}): EvaluationContext {
  const facts = new Map(APPS.map((a) => [a.appId, a]));
  return {
    facts: (id) => facts.get(id),
    universe: [1, 2, 3, 4],
    extended: [5],
    friendOwners: (id) => (id in owners ? owners[id] : []),
    definition: (id) => definitions.find((d) => d.id === id),
    now: NOW,
  };
}

function rules(list: Rule[], mode: "all" | "any" = "all", extra: Partial<GroupDefinition> = {}): GroupDefinition {
  return { id: "g", name: "G", kind: "rules", appIds: [], rules: { mode, rules: list }, added: [], hidden: [], ...extra };
}

const r = (type: Rule["type"], params: Record<string, unknown> = {}, inverted = false): Rule => ({ type, inverted, params });
const run = (list: Rule[], mode: "all" | "any" = "all", c = ctx()) => evaluateGroup(rules(list, mode), c);

describe("evaluateGroup", () => {
  it.each<[string, Rule, number[]]>([
    ["installed", r("installed"), [1, 3]],
    ["not installed", r("installed", {}, true), [2, 4]],
    ["collection", r("collection", { id: "favorite" }), [1]],
    ["name", r("name", { text: "dead" }), [2]],
    ["kind", r("kind", { kinds: ["shortcut"] }), [3]],
    ["kind reaches music", r("kind", { kinds: ["music"] }), [5]],
    ["deck verified or playable", r("deckCompat", { levels: [2, 3] }), [1, 2]],
    ["steamos verified", r("steamosCompat", { levels: [3] }), [1]],
    ["tags any", r("tags", { ids: [122, 3959], match: "any" }), [1, 2]],
    ["tags all", r("tags", { ids: [122, 3959], match: "all" }), [1]],
    ["features", r("features", { ids: [28], match: "any" }), [1]],
    ["playtime more", r("playtime", { op: "more", hours: 5 }), [1]],
    ["playtime less", r("playtime", { op: "less", hours: 5 }), [2, 3, 4]],
    ["last played more than", r("lastPlayed", { op: "more", days: 30 }), [2]],
    ["last played within", r("lastPlayed", { op: "less", days: 30 }), [1]],
    ["never played", r("lastPlayed", { op: "never" }), [3, 4]],
    ["released within days", r("released", { op: "within", days: 30 }), [2]],
    ["released before", r("released", { op: "before", date: NOW - 100 * DAY }), [1]],
    ["purchased after", r("purchased", { op: "after", date: NOW - 500 * DAY }), [1]],
    ["size more", r("size", { op: "more", gb: 10 }), [1]],
    ["metacritic", r("review", { source: "metacritic", op: "more", value: 90 }), [1]],
    ["steam reviews less", r("review", { source: "steam", op: "less", value: 95 }), [2]],
    ["achievements percent", r("achievements", { measure: "percent", op: "more", value: 50 }), [1]],
    ["achievements count", r("achievements", { measure: "count", op: "less", value: 5 }), [2]],
    ["family shared", r("familyShared"), [2]],
    ["demo", r("demo"), [4]],
    ["coming soon", r("comingSoon"), [4]],
    ["streamable", r("streamable"), [1]],
    ["any sd card", r("sdCard"), [3]],
    ["one sd card", r("sdCard", { card: "card-b" }), []],
    ["install folder", r("installFolder", { folder: "1" }), [3]],
    ["name pattern", r("name", { pattern: "^d(ead|emo)" }), [2, 4]],
    ["broken pattern", r("name", { pattern: "(" }), []],
    ["size in GiB at least", r("size", { op: "atLeast", gb: 15e9 / 1024 ** 3 }), [1]],
    ["metacritic at most", r("review", { source: "metacritic", op: "atMost", value: 89 }), [2]],
    ["release date unknown", r("released", { op: "unknown" }), [3, 4]],
    ["last played older than", r("lastPlayed", { op: "more", days: 1 }), [1, 2]],
    ["released older than", r("released", { op: "olderThan", days: 100 }), [1]],
    ["sd card in the slot", r("sdCard", { card: "current" }), [3]],
    ["games list", r("games", { ids: [4, 2] }), [2, 4]],
  ])("%s", (_name, rule, expected) => {
    expect(run([rule])).toEqual(expected);
  });

  it("an unknown value matches neither the rule nor its opposite", () => {
    expect(run([r("review", { source: "metacritic", op: "less", value: 100 })])).toEqual([1, 2]);
    expect(run([r("review", { source: "metacritic", op: "less", value: 100 }, true)])).toEqual([]);
  });

  it("combines rules with all or any, and nests them", () => {
    expect(run([r("installed"), r("tags", { ids: [3959], match: "any" })], "all")).toEqual([1]);
    expect(run([r("installed"), r("demo")], "any")).toEqual([1, 3, 4]);
    expect(run([r("installed"), r("all", { mode: "any", rules: [r("demo"), r("familyShared")] })], "any")).toEqual([1, 2, 3, 4]);
  });

  it("an empty rule list matches nothing", () => {
    expect(run([])).toEqual([]);
  });

  it("keeps added games and leaves hidden ones out", () => {
    const group = rules([r("installed")], "all", { added: [4], hidden: [3] });
    expect(evaluateGroup(group, ctx())).toEqual([1, 4]);
  });

  it("a group can also look at software, music or tools", () => {
    expect(evaluateGroup(rules([r("installed")], "all", { include: ["music"] }), ctx())).toEqual([1, 3, 5]);
  });

  it("a manual group is its picked games minus hidden ones", () => {
    const group: GroupDefinition = { id: "m", name: "M", kind: "manual", appIds: [2, 1, 99], added: [], hidden: [1] };
    expect(evaluateGroup(group, ctx())).toEqual([2]);
  });

  it("uses another group as a rule and stops at cycles", () => {
    const a = rules([r("group", { id: "b" })], "all", { id: "a" });
    const b = rules([r("group", { id: "a" })], "any", { id: "b" });
    const installed = rules([r("installed")], "all", { id: "i" });
    const c = ctx([a, b, installed]);
    expect(evaluateGroup(a, c)).toEqual([]);
    expect(evaluateGroup(rules([r("group", { id: "i" })]), c)).toEqual([1, 3]);
    expect(evaluateGroup(rules([r("group", { id: "missing" })]), c)).toEqual([]);
  });

  it("friends: owned by any, by all of some, and not known yet", () => {
    const c = ctx([], { 1: ["x", "y"], 2: ["y"], 3: null });
    expect(evaluateGroup(rules([r("friends", { ids: [], match: "any" })]), c)).toEqual([1, 2]);
    expect(evaluateGroup(rules([r("friends", { ids: ["x", "y"], match: "all" })]), c)).toEqual([1]);
    expect(evaluateGroup(rules([r("friends", { ids: [], match: "any" }, true)]), c)).toEqual([4]);
  });

  it("deeper nesting than allowed matches nothing", () => {
    let rule: Rule = r("installed");
    for (let i = 0; i < 4; i++) rule = r("all", { mode: "all", rules: [rule] });
    expect(run([rule])).toEqual([]);
  });
});
