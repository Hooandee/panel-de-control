import { describe, it, expect } from "vitest";
import { parseHidden } from "./hidden";

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
