import { describe, expect, it } from "vitest";
import { activeThreads, formatGhz, threadsPerCore, turboFraction } from "./cpu";

describe("formatGhz", () => {
  it("converts kHz to GHz with one decimal", () => {
    expect(formatGhz(5_100_000)).toBe("5.1 GHz");
    expect(formatGhz(3_300_000)).toBe("3.3 GHz");
  });
  it("returns dash for null/invalid", () => {
    expect(formatGhz(null)).toBe("—");
    expect(formatGhz(0)).toBe("—");
  });
});

describe("turboFraction", () => {
  it("is the tail above base over max", () => {
    expect(turboFraction(4_000_000, 5_000_000)).toBeCloseTo(0.2, 5);
  });
  it("is 0 when missing or max<=base", () => {
    expect(turboFraction(null, 5_000_000)).toBe(0);
    expect(turboFraction(5_000_000, 5_000_000)).toBe(0);
    expect(turboFraction(5_000_000, 4_000_000)).toBe(0);
  });
});

describe("threadsPerCore", () => {
  it("is 2 on SMT (16 threads / 8 cores)", () => {
    expect(threadsPerCore(8, 16)).toBe(2);
  });
  it("is 1 with no hyperthreading (Lunar Lake: threads == cores)", () => {
    expect(threadsPerCore(8, 8)).toBe(1);
  });
  it("falls back to 1 on missing data", () => {
    expect(threadsPerCore(null, 16)).toBe(1);
    expect(threadsPerCore(8, null)).toBe(1);
  });
});

describe("activeThreads", () => {
  it("is all threads with SMT on, cores with it off", () => {
    expect(activeThreads(8, 16, true)).toBe(16);
    expect(activeThreads(8, 16, false)).toBe(8);
  });
});
