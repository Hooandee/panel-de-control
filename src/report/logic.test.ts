import { describe, it, expect } from "vitest";
import { REPORT_CATEGORIES, canSubmit, toggleCategory } from "./logic";

describe("toggleCategory", () => {
  it("adds when absent", () => {
    expect(toggleCategory([], "tdp")).toEqual(["tdp"]);
  });
  it("removes when present", () => {
    expect(toggleCategory(["tdp", "fans"], "tdp")).toEqual(["fans"]);
  });
  it("does not mutate the input", () => {
    const sel: ("tdp")[] = ["tdp"];
    toggleCategory(sel, "tdp");
    expect(sel).toEqual(["tdp"]);
  });
});

describe("canSubmit", () => {
  it("false for an empty report", () => {
    expect(canSubmit([], "")).toBe(false);
    expect(canSubmit([], "   ")).toBe(false);
  });
  it("true with a category", () => {
    expect(canSubmit(["fans"], "")).toBe(true);
  });
  it("true with only free text", () => {
    expect(canSubmit([], "algo falla")).toBe(true);
  });
});

describe("REPORT_CATEGORIES", () => {
  it("includes the expected ids", () => {
    expect(REPORT_CATEGORIES).toContain("tdp");
    expect(REPORT_CATEGORIES).toContain("other");
  });
});
