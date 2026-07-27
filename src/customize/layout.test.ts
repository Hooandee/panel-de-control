import { describe, it, expect } from "vitest";
import { orderIds, visibleIds, move, toggle, coerceLayout, subitemHidden, ensure, pinnedLast } from "./layout";

describe("ensure (idempotent hide)", () => {
  it("adds when absent, no-op when present", () => {
    expect(ensure([], "a")).toEqual(["a"]);
    expect(ensure(["b"], "a")).toEqual(["b", "a"]);
    expect(ensure(["a"], "a")).toEqual(["a"]);
  });
});

describe("pinnedLast", () => {
  it("moves the pinned id to the end (new tab appended after settings)", () => {
    expect(pinnedLast(["system", "settings", "view:v1"], "settings")).toEqual(["system", "view:v1", "settings"]);
  });
  it("no-op when already last or absent", () => {
    expect(pinnedLast(["a", "settings"], "settings")).toEqual(["a", "settings"]);
    expect(pinnedLast(["a", "b"], "settings")).toEqual(["a", "b"]);
  });
});

describe("coerceLayout", () => {
  const EMPTY = { tabs: { order: [], hidden: [] }, blocks: {}, subitems: {} };

  it("returns empty layout for non-object input", () => {
    expect(coerceLayout(null)).toEqual(EMPTY);
    expect(coerceLayout(5)).toEqual(EMPTY);
    expect(coerceLayout("x")).toEqual(EMPTY);
    expect(coerceLayout([])).toEqual(EMPTY);
  });

  it("keeps a well-formed layout", () => {
    const good = {
      tabs: { order: ["a"], hidden: ["b"] },
      blocks: { sys: { order: ["x"], hidden: [] } },
      subitems: { battery: ["health"] },
    };
    expect(coerceLayout(good)).toEqual(good);
  });

  it("defaults subitems to {} when the stored layout predates it", () => {
    const old = { tabs: { order: ["a"], hidden: [] }, blocks: {} };
    expect(coerceLayout(old)).toEqual({ ...old, subitems: {} });
  });

  it("coerces wrong-typed fields to safe arrays (never throws downstream)", () => {
    // valid JSON, wrong types — the bug that bricked the panel (for..of on a number)
    expect(coerceLayout({ tabs: { order: 5, hidden: {} } })).toEqual(EMPTY);
    expect(coerceLayout({ tabs: 5, blocks: [] })).toEqual(EMPTY);
    // non-string ids are dropped
    expect(coerceLayout({ tabs: { order: ["a", 1, null], hidden: [] } }))
      .toEqual({ tabs: { order: ["a"], hidden: [] }, blocks: {}, subitems: {} });
    // a block pref with a bad shape coerces, doesn't crash
    expect(coerceLayout({ blocks: { sys: { order: 9 } } }))
      .toEqual({ tabs: { order: [], hidden: [] }, blocks: { sys: { order: [], hidden: [] } }, subitems: {} });
    // a corrupt subitems map coerces to {}
    expect(coerceLayout({ subitems: 7 })).toEqual(EMPTY);
    // a subitems entry with a wrong-typed value coerces to an empty id list
    expect(coerceLayout({ subitems: { battery: 9 } }))
      .toEqual({ ...EMPTY, subitems: { battery: [] } });
    // non-string ids inside a subitems list are dropped
    expect(coerceLayout({ subitems: { battery: ["health", 1, null] } }))
      .toEqual({ ...EMPTY, subitems: { battery: ["health"] } });
  });
});

describe("subitemHidden", () => {
  it("is true only for an id listed as hidden in its group", () => {
    const subitems = { battery: ["health"] };
    expect(subitemHidden(subitems, "battery", "health")).toBe(true);
    expect(subitemHidden(subitems, "battery", "cycles")).toBe(false);
    expect(subitemHidden(subitems, "cpu", "health")).toBe(false);
    expect(subitemHidden({}, "battery", "health")).toBe(false);
  });
});

describe("orderIds", () => {
  const defaults = ["a", "b", "c"];

  it("returns defaults in order when no pref", () => {
    expect(orderIds(defaults, undefined)).toEqual(["a", "b", "c"]);
    expect(orderIds(defaults, [])).toEqual(["a", "b", "c"]);
  });

  it("honors a stored order", () => {
    expect(orderIds(defaults, ["c", "a", "b"])).toEqual(["c", "a", "b"]);
  });

  it("drops ids no longer in defaults (stale)", () => {
    expect(orderIds(defaults, ["c", "x", "a"])).toEqual(["c", "a", "b"]);
  });

  it("appends new defaults not yet in the stored order (visible)", () => {
    // 'c' is new since the pref was saved → goes last, not lost.
    expect(orderIds(defaults, ["b", "a"])).toEqual(["b", "a", "c"]);
  });

  it("dedupes a corrupt order with repeats", () => {
    expect(orderIds(defaults, ["a", "a", "b"])).toEqual(["a", "b", "c"]);
  });
});

describe("visibleIds", () => {
  const defaults = ["a", "b", "c"];

  it("filters out hidden ids, keeping order", () => {
    expect(visibleIds(defaults, { order: ["c", "a", "b"], hidden: ["a"] })).toEqual(["c", "b"]);
  });

  it("shows all when nothing hidden", () => {
    expect(visibleIds(defaults, { order: [], hidden: [] })).toEqual(["a", "b", "c"]);
    expect(visibleIds(defaults, undefined)).toEqual(["a", "b", "c"]);
  });

  it("keeps a pinned id visible even if hidden is set", () => {
    expect(visibleIds(defaults, { order: [], hidden: ["a", "b"] }, ["a"])).toEqual(["a", "c"]);
  });
});

describe("move", () => {
  const list = ["a", "b", "c"];

  it("moves an item up", () => {
    expect(move(list, "b", -1)).toEqual(["b", "a", "c"]);
  });

  it("moves an item down", () => {
    expect(move(list, "b", 1)).toEqual(["a", "c", "b"]);
  });

  it("is a no-op at the edges", () => {
    expect(move(list, "a", -1)).toEqual(["a", "b", "c"]);
    expect(move(list, "c", 1)).toEqual(["a", "b", "c"]);
  });

  it("is a no-op for an unknown id", () => {
    expect(move(list, "x", 1)).toEqual(["a", "b", "c"]);
  });

  it("does not mutate the input", () => {
    const input = ["a", "b", "c"];
    move(input, "a", 1);
    expect(input).toEqual(["a", "b", "c"]);
  });
});

describe("toggle", () => {
  it("adds an id not present", () => {
    expect(toggle(["a"], "b")).toEqual(["a", "b"]);
  });

  it("removes an id present", () => {
    expect(toggle(["a", "b"], "a")).toEqual(["b"]);
  });

  it("does not mutate the input", () => {
    const input = ["a"];
    toggle(input, "b");
    expect(input).toEqual(["a"]);
  });
});
