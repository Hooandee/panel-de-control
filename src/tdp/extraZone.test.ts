import { describe, expect, it } from "vitest";
import { extraZone, manualCeiling } from "./extraZone";

describe("extraZone", () => {
  it("classifies requests against the safe range", () => {
    expect(extraZone(4, 7, 30)).toBe("low");
    expect(extraZone(7, 7, 30)).toBeNull();
    expect(extraZone(30, 7, 30)).toBeNull();
    expect(extraZone(36, 7, 30)).toBe("high");
  });
});

describe("manualCeiling", () => {
  it("offers the extra range only on the charger", () => {
    expect(manualCeiling(30, true, 40)).toBe(40);
    expect(manualCeiling(25, false, 40)).toBe(25);
    expect(manualCeiling(30, true, undefined)).toBe(30);
  });
});
