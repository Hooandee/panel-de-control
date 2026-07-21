import { describe, it, expect } from "vitest";
import { commitHiddenChange, parseHidden } from "./hidden";

describe("parseHidden", () => {
  it("parses a JSON array of stable keys", () => {
    expect(parseHidden('["a","b","c"]')).toEqual(["a", "b", "c"]);
  });

  it("null / empty → []", () => {
    expect(parseHidden(null)).toEqual([]);
    expect(parseHidden("")).toEqual([]);
  });

  it("garbage / non-array → []", () => {
    expect(parseHidden("not json")).toEqual([]);
    expect(parseHidden('{"a":1}')).toEqual([]);
    expect(parseHidden("42")).toEqual([]);
  });

  it("drops non-string entries and dedupes", () => {
    expect(parseHidden('["a",1,"a",null,"b"]')).toEqual(["a", "b"]);
  });
});

describe("commitHiddenChange", () => {
  it("keeps the new list only when durable persistence confirms it", async () => {
    await expect(commitHiddenChange(["a"], ["a", "b"], async () => true)).resolves.toEqual({
      value: ["a", "b"],
      saved: true,
    });
  });

  it("returns the previous list when durable persistence fails", async () => {
    await expect(
      commitHiddenChange(["a"], ["a", "b"], async () => {
        throw new Error("offline");
      }),
    ).resolves.toEqual({ value: ["a"], saved: false });
  });
});
