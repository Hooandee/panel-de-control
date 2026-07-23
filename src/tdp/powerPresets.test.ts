import { describe, it, expect } from "vitest";
import { resolveItems, BUILTIN_IDS } from "./powerPresets";
import type { PowerPresetState } from "../api";

const builtinWatts = { quiet: 8, balanced: 15, turbo: 25, turbo_ac: 30 };
const base: PowerPresetState = { order: [...BUILTIN_IDS], hidden: [], custom: {} };

describe("resolveItems", () => {
  it("lists the 3 builtins with device watts (battery)", () => {
    const r = resolveItems(base, builtinWatts, false, 15);
    expect(r.visible.map((i) => i.id)).toEqual(["quiet", "balanced", "turbo"]);
    expect(r.visible.map((i) => i.watts)).toEqual([8, 15, 25]);
    expect(r.anyHidden).toBe(false);
    expect(r.allHidden).toBe(false);
  });

  it("turbo uses the AC watts on charger", () => {
    const r = resolveItems(base, builtinWatts, true, 15);
    expect(r.visible.find((i) => i.id === "turbo")!.watts).toBe(30);
  });

  it("marks the item matching current watts active", () => {
    const r = resolveItems(base, builtinWatts, false, 25);
    expect(r.visible.find((i) => i.active)!.id).toBe("turbo");
  });

  it("orders custom after builtins and labels by watts", () => {
    const st: PowerPresetState = {
      order: ["quiet", "balanced", "turbo", "c1"],
      hidden: [],
      custom: { c1: { watts: 12, icon: "bolt", boost: null } },
    };
    const r = resolveItems(st, builtinWatts, false, 12);
    const c = r.visible.find((i) => i.id === "c1")!;
    expect(c.watts).toBe(12);
    expect(c.label).toBe("12W");
    expect(c.deletable).toBe(true);
    expect(c.active).toBe(true);
  });

  it("hides hidden ids from visible but keeps them in manager list", () => {
    const st: PowerPresetState = { order: [...BUILTIN_IDS], hidden: ["turbo"], custom: {} };
    const r = resolveItems(st, builtinWatts, false, 8);
    expect(r.visible.map((i) => i.id)).toEqual(["quiet", "balanced"]);
    expect(r.manager.map((i) => i.id)).toEqual(["quiet", "balanced", "turbo"]);
    expect(r.manager.find((i) => i.id === "turbo")!.hidden).toBe(true);
    expect(r.anyHidden).toBe(true);
  });

  it("flags allHidden when nothing is visible", () => {
    const st: PowerPresetState = { order: [...BUILTIN_IDS], hidden: [...BUILTIN_IDS], custom: {} };
    const r = resolveItems(st, builtinWatts, false, 8);
    expect(r.visible).toEqual([]);
    expect(r.allHidden).toBe(true);
  });

  it("builtins are not deletable or editable", () => {
    const r = resolveItems(base, builtinWatts, false, 8);
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
    const r = resolveItems(st, builtinWatts, false, 8);
    expect(r.manager.map((i) => i.id)).toEqual(["quiet", "balanced", "turbo"]);
  });
});
