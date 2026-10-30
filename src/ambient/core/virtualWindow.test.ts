import { describe, expect, it } from "vitest";

import { nearEnd, visibleRange } from "./virtualWindow";

describe("virtual window", () => {
  it("renders visible rows plus overscan", () => {
    expect(visibleRange(0, 280, 56, 400)).toEqual({ start: 0, end: 12 });
    expect(visibleRange(56 * 100, 280, 56, 400)).toEqual({ start: 94, end: 112 });
  });

  it("clamps at both ends", () => {
    expect(visibleRange(-50, 280, 56, 3)).toEqual({ start: 0, end: 3 });
    expect(visibleRange(56 * 399, 280, 56, 400).end).toBe(400);
    expect(visibleRange(0, 280, 56, 0)).toEqual({ start: 0, end: 0 });
  });

  it("asks for the next page near the end", () => {
    expect(nearEnd({ start: 20, end: 33 }, 40)).toBe(true);
    expect(nearEnd({ start: 0, end: 12 }, 40)).toBe(false);
  });
});
