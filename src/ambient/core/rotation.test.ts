import { describe, expect, it } from "vitest";

import { advance, createRotation, shouldAdvance } from "./rotation";

function seeded(seed: number) {
  let s = seed;
  return () => {
    s = (s * 1103515245 + 12345) % 2147483648;
    return s / 2147483648;
  };
}

describe("rotation", () => {
  it("walks sequentially and wraps", () => {
    let state = createRotation("sequential");
    const seen: (string | null)[] = [];
    for (let i = 0; i < 4; i += 1) {
      state = advance(state, ["a", "b", "c"]);
      seen.push(state.current);
    }
    expect(seen).toEqual(["a", "b", "c", "a"]);
  });

  it("shuffle shows every item once per cycle", () => {
    const ids = ["a", "b", "c", "d", "e"];
    let state = createRotation("shuffle");
    const random = seeded(7);
    for (let cycle = 0; cycle < 3; cycle += 1) {
      const seen = new Set<string>();
      for (let i = 0; i < ids.length; i += 1) {
        state = advance(state, ids, random);
        seen.add(state.current as string);
      }
      expect(seen.size).toBe(ids.length);
    }
  });

  it("shuffle never repeats the same item across a cycle boundary", () => {
    let state = createRotation("shuffle");
    const random = seeded(3);
    let previous: string | null = null;
    for (let i = 0; i < 60; i += 1) {
      state = advance(state, ["a", "b", "c"], random);
      expect(state.current).not.toBe(previous);
      previous = state.current;
    }
  });

  it("drops removed items from the pending queue", () => {
    let state = advance(createRotation("shuffle"), ["a", "b", "c"], seeded(1));
    state = advance(state, ["a"], seeded(1));
    expect(state.current).toBe("a");
  });

  it("empty collection yields nothing", () => {
    expect(advance(createRotation("shuffle"), []).current).toBeNull();
  });

  it("advances on interval or on return home", () => {
    expect(shouldAdvance(299_000, 300, false, false)).toBe(false);
    expect(shouldAdvance(300_000, 300, false, false)).toBe(true);
    expect(shouldAdvance(10_000_000, 300, false, true)).toBe(false);
    expect(shouldAdvance(0, 300, true, true)).toBe(true);
  });
});
