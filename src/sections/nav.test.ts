import { describe, it, expect } from "vitest";
import { resolveActiveSection, cycleTab } from "./nav";

// The section registry + active id are the single source of truth for the shell.
// The navigator (TabBar today, maybe a dropdown later) is just presentation.
// resolveActiveSection picks which section to render, falling back safely.

const SECTIONS = [{ id: "power" }, { id: "system" }];

describe("resolveActiveSection", () => {
  it("returns the section matching the active id", () => {
    expect(resolveActiveSection(SECTIONS, "system")).toEqual({ id: "system" });
  });
  it("falls back to the first section for an unknown id", () => {
    expect(resolveActiveSection(SECTIONS, "nope")).toEqual({ id: "power" });
  });
  it("returns undefined when there are no sections", () => {
    expect(resolveActiveSection([], "power")).toBeUndefined();
  });
});

describe("cycleTab", () => {
  const ids = ["power", "system", "fans"];

  it("moves to the next tab", () => {
    expect(cycleTab(ids, "power", 1)).toBe("system");
  });
  it("moves to the previous tab", () => {
    expect(cycleTab(ids, "system", -1)).toBe("power");
  });
  it("wraps forward past the last tab", () => {
    expect(cycleTab(ids, "fans", 1)).toBe("power");
  });
  it("wraps backward past the first tab", () => {
    expect(cycleTab(ids, "power", -1)).toBe("fans");
  });
  it("returns the active id unchanged when it isn't in the list", () => {
    expect(cycleTab(ids, "nope", 1)).toBe("nope");
  });
  it("returns the active id unchanged for an empty list", () => {
    expect(cycleTab([], "power", 1)).toBe("power");
  });
});
