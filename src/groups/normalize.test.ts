import { describe, expect, it } from "vitest";

import { normalizeGroup, normalizeGroups } from "./normalize";

const RULES = { id: "grp:a", name: " RPG ", kind: "rules", appIds: [], added: [7], hidden: [8],
  rules: { mode: "all", rules: [{ type: "installed", inverted: false, params: {} }] } };
const MANUAL = { id: "grp:m", name: "Mine", kind: "manual", appIds: [3, 3, 0, -1, 2 ** 32, 5], added: [], hidden: [] };

describe("normalizeGroup", () => {
  it("keeps valid groups and cleans their lists", () => {
    expect(normalizeGroup(RULES)).toEqual({ ...RULES, name: "RPG" });
    expect(normalizeGroup(MANUAL)).toEqual({ ...MANUAL, appIds: [3, 5] });
  });

  it.each([
    ["no id", { ...MANUAL, id: "" }],
    ["bad id", { ...MANUAL, id: "a b" }],
    ["empty name", { ...MANUAL, name: "  " }],
    ["unknown kind", { ...MANUAL, kind: "smart" }],
    ["rules without rule set", { ...RULES, rules: undefined }],
    ["manual without games list", { ...MANUAL, appIds: "1,2" }],
  ])("drops %s", (_name, value) => {
    expect(normalizeGroup(value)).toBeNull();
  });

  it("drops unknown or malformed rules but keeps the group", () => {
    const group = normalizeGroup({ ...RULES, rules: { mode: "any", rules: [
      { type: "telepathy", inverted: false, params: {} },
      { type: "installed", inverted: "no", params: {} },
      { type: "name", inverted: true, params: { text: "x" } },
    ] } });
    expect(group?.rules).toEqual({ mode: "any", rules: [{ type: "name", inverted: true, params: { text: "x" } }] });
  });

  it("drops nesting deeper than three levels", () => {
    let rule: Record<string, unknown> = { type: "installed", inverted: false, params: {} };
    for (let i = 0; i < 4; i++) rule = { type: "all", inverted: false, params: { mode: "all", rules: [rule] } };
    const depth = (set: { rules: { type: string; params: Record<string, unknown> }[] } | undefined): number =>
      set?.rules[0]?.type === "all" ? 1 + depth(set.rules[0].params as never) : 0;
    expect(depth(normalizeGroup({ ...RULES, rules: { mode: "all", rules: [rule] } })?.rules as never)).toBe(3);
  });

  it("caps manual games at 200", () => {
    const many = Array.from({ length: 250 }, (_, i) => i + 1);
    expect(normalizeGroup({ ...MANUAL, appIds: many })?.appIds).toHaveLength(200);
  });
});

describe("normalizeGroups", () => {
  it("keeps the good records, in order, without duplicates, up to 100", () => {
    expect(normalizeGroups([MANUAL, { bad: true }, RULES, MANUAL]).map((g) => g.id)).toEqual(["grp:m", "grp:a"]);
    const many = Array.from({ length: 120 }, (_, i) => ({ ...MANUAL, id: `grp:${i}` }));
    expect(normalizeGroups(many)).toHaveLength(100);
    expect(normalizeGroups("nope")).toEqual([]);
  });
});
