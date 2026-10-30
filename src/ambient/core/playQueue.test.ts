import { describe, expect, it } from "vitest";

import {
  clear, current, emptyQueue, enqueue, fromItems, goTo, move, nextPosition, previousPosition, remove, setRepeat, setShuffle,
  type QueueState,
} from "./playQueue";

const items = (state: QueueState<string>) => state.entries.map((e) => e.item);
const reverse = () => 0;

describe("play queue", () => {
  it("adds at the end or right after the one playing", () => {
    let q = fromItems(emptyQueue<string>(), ["a", "b", "c"], 1);
    q = enqueue(q, ["x", "y"]);
    q = enqueue(q, ["n"], "next");
    expect(items(q)).toEqual(["a", "b", "n", "c", "x", "y"]);
    expect(current(q)?.item).toBe("b");
  });

  it("keeps duplicates apart so each can be removed on its own", () => {
    let q = enqueue(emptyQueue<string>(), ["a", "a"]);
    q = remove(q, q.entries[1].key).state;
    expect(items(q)).toEqual(["a"]);
  });

  it("repeat all wraps, repeat one stays on ended but skips on demand, off stops at the end", () => {
    const q = fromItems(emptyQueue<string>(), ["a", "b"], 1);
    expect(nextPosition(q, "ended")).toBe(0);
    expect(nextPosition(setRepeat(q, "one"), "ended")).toBe(1);
    expect(nextPosition(setRepeat(q, "one"), "skip")).toBe(0);
    expect(nextPosition(setRepeat(q, "off"), "ended")).toBeNull();
    expect(nextPosition(setRepeat(q, "off"), "skip")).toBe(0);
    expect(previousPosition(fromItems(q, ["a", "b"], 0))).toBe(1);
    expect(previousPosition(setRepeat(fromItems(q, ["a", "b"], 0), "off"))).toBe(0);
    expect(nextPosition(emptyQueue<string>(), "ended")).toBeNull();
  });

  it("removing the one playing hands over to what follows, or the one before at the end", () => {
    let q = fromItems(emptyQueue<string>(), ["a", "b", "c"], 1);
    let result = remove(q, q.entries[1].key);
    expect(result.currentChanged).toBe(true);
    expect(current(result.state)?.item).toBe("c");
    q = fromItems(q, ["a", "b"], 1);
    result = remove(q, q.entries[1].key);
    expect(current(result.state)?.item).toBe("a");
    q = fromItems(q, ["a", "b", "c"], 2);
    result = remove(q, q.entries[0].key);
    expect(result.currentChanged).toBe(false);
    expect(current(result.state)?.item).toBe("c");
  });

  it("moving entries keeps the one playing", () => {
    let q = fromItems(emptyQueue<string>(), ["a", "b", "c", "d"], 1);
    q = move(q, q.entries[3].key, 0);
    expect(items(q)).toEqual(["d", "a", "b", "c"]);
    expect(current(q)?.item).toBe("b");
    q = move(q, q.entries[2].key, 3);
    expect(items(q)).toEqual(["d", "a", "c", "b"]);
    expect(current(q)?.item).toBe("b");
  });

  it("shuffle mixes only what is left and turning it off restores the original order", () => {
    let q = fromItems(emptyQueue<string>(), ["a", "b", "c", "d"], 1);
    q = setShuffle(q, true, reverse);
    expect(items(q).slice(0, 2)).toEqual(["a", "b"]);
    expect([...items(q).slice(2)].sort()).toEqual(["c", "d"]);
    q = enqueue(q, ["e"]);
    q = setShuffle(q, false);
    expect(items(q)).toEqual(["a", "b", "c", "d", "e"]);
    expect(current(q)?.item).toBe("b");
  });

  it("a shuffled queue starts on the chosen item and mixes again when it wraps", () => {
    let q = fromItems({ ...emptyQueue<string>(), shuffle: true }, ["a", "b", "c", "d"], 2, reverse);
    expect(current(q)?.item).toBe("c");
    expect(q.position).toBe(0);
    q = goTo(q, q.entries.length - 1);
    const wrapped = goTo(q, 0, reverse);
    expect(wrapped.position).toBe(0);
    expect([...items(wrapped)].sort()).toEqual(["a", "b", "c", "d"]);
  });

  it("clearing empties it", () => {
    expect(clear(fromItems(emptyQueue<string>(), ["a"])).entries).toEqual([]);
  });
});
