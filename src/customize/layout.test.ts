import { describe, it, expect } from "vitest";
import { orderIds, visibleIds, move, toggle } from "./layout";

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
