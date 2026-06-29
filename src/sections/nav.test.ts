import { describe, it, expect } from "vitest";
import { resolveActiveSection } from "./nav";

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
