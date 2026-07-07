import { describe, expect, it } from "vitest";

import { shouldSuppress } from "./valueToastLogic";

describe("shouldSuppress", () => {
  it("does not suppress when there was no self-write", () => {
    expect(shouldSuppress(null, 1000, 1500)).toBe(false);
  });

  it("suppresses an echo shortly after a self-write", () => {
    expect(shouldSuppress(1000, 1500, 1500)).toBe(true);
  });

  it("does not suppress once the window has fully passed", () => {
    expect(shouldSuppress(1000, 3000, 1500)).toBe(false);
  });

  it("does not suppress exactly at the window boundary", () => {
    expect(shouldSuppress(1000, 2500, 1500)).toBe(false);
  });

  it("suppresses just inside the window boundary", () => {
    expect(shouldSuppress(1000, 2499, 1500)).toBe(true);
  });
});
