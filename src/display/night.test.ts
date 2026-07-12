import { describe, expect, it } from "vitest";
import { toHHMM, stepMinutes } from "./night";

describe("toHHMM", () => {
  it("zero-pads hours and minutes", () => {
    expect(toHHMM(0)).toBe("00:00");
    expect(toHHMM(9 * 60 + 5)).toBe("09:05");
    expect(toHHMM(22 * 60)).toBe("22:00");
    expect(toHHMM(23 * 60 + 45)).toBe("23:45");
  });
});

describe("stepMinutes", () => {
  it("steps by hour (size 60) with day wrap", () => {
    expect(stepMinutes(23 * 60, 1, 60)).toBe(0);        // 23:00 +1h → 00:00
    expect(stepMinutes(0, -1, 60)).toBe(23 * 60);       // 00:00 -1h → 23:00
  });

  it("steps by 15 minutes, carrying into the hour", () => {
    expect(stepMinutes(22 * 60 + 45, 1, 15)).toBe(23 * 60); // 22:45 +15 → 23:00
    expect(stepMinutes(0, -1, 15)).toBe(23 * 60 + 45);      // 00:00 -15 → 23:45
  });
});
