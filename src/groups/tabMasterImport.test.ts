import { describe, expect, it } from "vitest";

import { translateTabMasterTab } from "./tabMasterImport";

const tab = (filters: unknown[], over: Record<string, unknown> = {}) =>
  ({ id: "a1b2", title: "RPG", position: 1, filters, filtersMode: "and", categoriesToInclude: 1, ...over });
const f = (type: string, params: Record<string, unknown>, inverted = false) => ({ type, inverted, params });
const rulesOf = (filters: unknown[], over: Record<string, unknown> = {}) => translateTabMasterTab(tab(filters, over))?.group.rules?.rules;

describe("translateTabMasterTab", () => {
  it("leaves Steam's own tabs out", () => {
    expect(translateTabMasterTab({ id: "AllGames", title: "All", position: 0 })).toBeNull();
    expect(translateTabMasterTab(tab([]))).toBeNull();
  });

  it("names the group after the tab and remembers where it came from", () => {
    const imported = translateTabMasterTab(tab([f("installed", { installed: true })]));
    expect(imported?.group).toMatchObject({ id: "grp:tm-a1b2", name: "RPG", kind: "rules", importedFrom: "tabmaster:a1b2" });
    expect(imported?.unknown).toEqual([]);
  });

  it.each([
    ["installed", f("installed", { installed: false }), { type: "installed", inverted: true, params: {} }],
    ["inverted installed", f("installed", { installed: false }, true), { type: "installed", inverted: false, params: {} }],
    ["collection", f("collection", { id: "uc-1", name: "Mine" }), { type: "collection", inverted: false, params: { id: "uc-1" } }],
    ["regex", f("regex", { regex: "^the" }), { type: "name", inverted: false, params: { pattern: "^the" } }],
    ["tags", f("tags", { tags: [122, 3959], mode: "and" }), { type: "tags", inverted: false, params: { ids: [122, 3959], match: "all" } }],
    ["platform steam", f("platform", { platform: "steam" }), { type: "kind", inverted: true, params: { kinds: ["shortcut"] } }],
    ["deck", f("deck compatibility", { category: 3 }), { type: "deckCompat", inverted: false, params: { levels: [3] } }],
    ["review", f("review score", { scoreThreshold: 80, condition: "above", type: "metacritic" }), { type: "review", inverted: false, params: { source: "metacritic", op: "atLeast", value: 80 } }],
    ["time in minutes", f("time played", { timeThreshold: 90, condition: "below", units: "minutes" }), { type: "playtime", inverted: false, params: { op: "atMost", hours: 1.5 } }],
    ["size", f("size on disk", { gbThreshold: 50, condition: "above" }), { type: "size", inverted: false, params: { op: "atLeast", gb: 50 } }],
    ["last played days ago", f("last played", { daysAgo: 30, condition: "below" }), { type: "lastPlayed", inverted: false, params: { op: "more", days: 30 } }],
    ["release unknown", f("release date", { isUnknown: true, condition: "above" }), { type: "released", inverted: false, params: { op: "unknown" } }],
    ["release within days", f("release date", { daysAgo: 14, condition: "above" }), { type: "released", inverted: false, params: { op: "within", days: 14 } }],
    ["demo off", f("demo", { isDemo: false }), { type: "demo", inverted: true, params: {} }],
    ["features", f("steam features", { features: [28], mode: "or" }), { type: "features", inverted: false, params: { ids: [28], match: "any" } }],
    ["achievements", f("achievements", { threshold: 3, thresholdType: "count", condition: "below" }), { type: "achievements", inverted: false, params: { measure: "count", op: "atMost", value: 3 } }],
    ["sd card in slot", f("sd card", { card: 0 }), { type: "sdCard", inverted: false, params: { card: "current" } }],
    ["any sd card", f("sd card", { card: 1 }), { type: "sdCard", inverted: false, params: {} }],
    ["install folder", f("install folder", { driveName: "SD" }), { type: "installFolder", inverted: false, params: { folder: "SD" } }],
  ])("%s", (_name, filter, expected) => {
    expect(rulesOf([filter])).toEqual([expected]);
  });

  it("dates become exact bounds", () => {
    const [after] = rulesOf([f("purchase date", { date: { year: 2024 }, condition: "above" })]) ?? [];
    const [before] = rulesOf([f("purchase date", { date: { year: 2024, month: 2 }, condition: "below" })]) ?? [];
    expect(after.params).toEqual({ op: "after", date: Math.floor(new Date(2024, 0, 1).getTime() / 1000) });
    expect(before.params).toEqual({ op: "before", date: Math.floor(new Date(2024, 2, 1).getTime() / 1000) });
  });

  it("game lists become the group's own lists at the top, and rules elsewhere", () => {
    const any = translateTabMasterTab(tab([f("installed", { installed: true }), f("whitelist", { games: [7, 8] })], { filtersMode: "or" }));
    expect(any?.group).toMatchObject({ added: [7, 8], rules: { mode: "any", rules: [{ type: "installed" }] } });
    const all = translateTabMasterTab(tab([f("installed", { installed: true }), f("blacklist", { games: [9] })]));
    expect(all?.group).toMatchObject({ hidden: [9], rules: { mode: "all", rules: [{ type: "installed" }] } });
    expect(rulesOf([f("whitelist", { games: [1] })])).toEqual([{ type: "games", inverted: false, params: { ids: [1] } }]);
  });

  it("merges become nested rules", () => {
    expect(rulesOf([f("merge", { mode: "or", filters: [f("demo", { isDemo: true }), f("installed", { installed: true })] })])).toEqual([
      { type: "all", inverted: false, params: { mode: "any", rules: [
        { type: "demo", inverted: false, params: {} }, { type: "installed", inverted: false, params: {} }] } },
    ]);
  });

  it("software and music categories widen the group", () => {
    expect(translateTabMasterTab(tab([f("installed", { installed: true })], { categoriesToInclude: 1 | 2 | 8192 }))?.group.include).toEqual(["software", "music"]);
  });

  it("notes filters it cannot express and keeps the rest", () => {
    const imported = translateTabMasterTab(tab([f("telepathy", {}), f("installed", { installed: true })]));
    expect(imported?.unknown).toEqual(["telepathy"]);
    expect(imported?.group.rules?.rules).toHaveLength(1);
  });
});
