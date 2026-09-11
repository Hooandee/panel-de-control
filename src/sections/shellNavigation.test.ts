import { describe, expect, it } from "vitest";
import { resolveShellState } from "./shellNavigation";

const ids = ["power", "system", "settings"];

describe("resolveShellState", () => {
  it("opens Home when the new mode has never been stored", () => {
    expect(resolveShellState(null, "system", ids, true)).toEqual({ mode: "home", activeId: "system" });
  });

  it.each(["home", "detail", "tabs"] as const)("restores valid %s state", (mode) => {
    expect(resolveShellState(mode, "system", ids, true)).toEqual({ mode, activeId: "system" });
  });

  it("returns to Home when a detailed section disappears", () => {
    expect(resolveShellState("detail", "missing", ids, true)).toEqual({ mode: "home", activeId: "power" });
  });

  it("forces classic tabs when Home is hidden", () => {
    expect(resolveShellState("home", "system", ids, false)).toEqual({ mode: "tabs", activeId: "system" });
  });

  it("uses the first valid tab when Home is hidden and the id is stale", () => {
    expect(resolveShellState("detail", "missing", ids, false)).toEqual({ mode: "tabs", activeId: "power" });
  });

  it("keeps an empty shell safe", () => {
    expect(resolveShellState("detail", "power", [], true)).toEqual({ mode: "home", activeId: null });
    expect(resolveShellState("detail", "power", [], false)).toEqual({ mode: "tabs", activeId: null });
  });
});
