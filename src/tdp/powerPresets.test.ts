import { describe, it, expect } from "vitest";
import { resolveItems, BUILTIN_IDS } from "./powerPresets";
import type { PowerPresetState } from "../api";

const builtinWatts = { quiet: 8, balanced: 15, turbo: 25, turbo_ac: 30 };
const base: PowerPresetState = { order: [...BUILTIN_IDS], hidden: [], custom: {} };
const MAX = 100; // effectively no clamp for the builtin cases
const FLAT = { mode: "estable" as const, off2: 0, off3: 0 }; // neutral live boost

describe("resolveItems", () => {
  it("lists the 3 builtins with device watts (battery)", () => {
    const r = resolveItems(base, builtinWatts, false, 15, MAX, FLAT);
    expect(r.visible.map((i) => i.id)).toEqual(["quiet", "balanced", "turbo"]);
    expect(r.visible.map((i) => i.watts)).toEqual([8, 15, 25]);
    expect(r.allHidden).toBe(false);
  });

  it("turbo uses the AC watts on charger", () => {
    const r = resolveItems(base, builtinWatts, true, 15, MAX, FLAT);
    expect(r.visible.find((i) => i.id === "turbo")!.watts).toBe(30);
  });

  it("marks the item matching current watts active", () => {
    const r = resolveItems(base, builtinWatts, false, 25, MAX, FLAT);
    expect(r.visible.find((i) => i.active)!.id).toBe("turbo");
  });

  it("orders custom after builtins and labels by watts", () => {
    const st: PowerPresetState = {
      order: ["quiet", "balanced", "turbo", "c1"],
      hidden: [],
      custom: { c1: { watts: 12, icon: "bolt", name: "", boost: null } },
    };
    const r = resolveItems(st, builtinWatts, false, 12, MAX, FLAT);
    const c = r.visible.find((i) => i.id === "c1")!;
    expect(c.watts).toBe(12);
    expect(c.label).toBe("12W");
    expect(c.deletable).toBe(true);
    expect(c.active).toBe(true);
  });

  it("clamps a custom preset's shown watts to the active ceiling", () => {
    const st: PowerPresetState = {
      order: ["quiet", "balanced", "turbo", "c1"],
      hidden: [],
      custom: { c1: { watts: 60, icon: "bolt", name: "", boost: null } },
    };
    const r = resolveItems(st, builtinWatts, false, 25, 25, FLAT);
    const c = r.visible.find((i) => i.id === "c1")!;
    expect(c.watts).toBe(25);
    expect(c.label).toBe("25W");
    expect(c.active).toBe(true);
  });

  it("hides hidden ids from visible but keeps them in manager list", () => {
    const st: PowerPresetState = { order: [...BUILTIN_IDS], hidden: ["turbo"], custom: {} };
    const r = resolveItems(st, builtinWatts, false, 8, MAX, FLAT);
    expect(r.visible.map((i) => i.id)).toEqual(["quiet", "balanced"]);
    expect(r.manager.map((i) => i.id)).toEqual(["quiet", "balanced", "turbo"]);
    expect(r.manager.find((i) => i.id === "turbo")!.hidden).toBe(true);
  });

  it("flags allHidden when nothing is visible", () => {
    const st: PowerPresetState = { order: [...BUILTIN_IDS], hidden: [...BUILTIN_IDS], custom: {} };
    const r = resolveItems(st, builtinWatts, false, 8, MAX, FLAT);
    expect(r.visible).toEqual([]);
    expect(r.allHidden).toBe(true);
  });

  it("builtins are not deletable or editable", () => {
    const r = resolveItems(base, builtinWatts, false, 8, MAX, FLAT);
    const builtins = r.manager.filter((x) => (BUILTIN_IDS as readonly string[]).includes(x.id));
    for (const i of builtins) {
      expect(i.deletable).toBe(false);
      expect(i.editable).toBe(false);
    }
  });

  it("drops a custom id whose definition is missing", () => {
    const st: PowerPresetState = {
      order: ["quiet", "balanced", "turbo", "cX"],
      hidden: [],
      custom: {},
    };
    const r = resolveItems(st, builtinWatts, false, 8, MAX, FLAT);
    expect(r.manager.map((i) => i.id)).toEqual(["quiet", "balanced", "turbo"]);
  });

  // --- boost-aware active marking (two same-watt presets must not both light) ---

  const twoSameWatt: PowerPresetState = {
    order: ["quiet", "balanced", "turbo", "c1", "c2"],
    hidden: [],
    custom: {
      c1: { watts: 15, icon: "bolt", name: "", boost: null }, // watts-only
      c2: { watts: 15, icon: "flame", name: "", boost: { mode: "custom", off2: 8, off3: 4 } }, // boosted
    },
  };

  it("with a matching boost applied, only the boosted preset is active", () => {
    const live = { mode: "custom" as const, off2: 8, off3: 4 };
    const r = resolveItems(twoSameWatt, builtinWatts, false, 15, MAX, live);
    const actives = r.visible.filter((i) => i.active).map((i) => i.id);
    expect(actives).toEqual(["c2"]);
  });

  it("with no boost applied, only the watts-only preset is active (not the boosted one)", () => {
    const r = resolveItems(twoSameWatt, builtinWatts, false, 15, MAX, FLAT);
    const actives = r.visible.filter((i) => i.active).map((i) => i.id);
    // c1 (watts-only) + builtin balanced (also watts-only 15) light; c2 (boosted) does NOT.
    expect(actives).toContain("c1");
    expect(actives).not.toContain("c2");
  });

  it("custom-boost active only when the exact margins match", () => {
    const live = { mode: "custom" as const, off2: 6, off3: 4 }; // different off2
    const r = resolveItems(twoSameWatt, builtinWatts, false, 15, MAX, live);
    expect(r.visible.find((i) => i.id === "c2")!.active).toBe(false);
  });
});
