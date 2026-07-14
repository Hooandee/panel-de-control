import { describe, it, expect } from "vitest";
import { scopeFor } from "./scope";

describe("scopeFor", () => {
  it("is global when no game is running", () => {
    expect(scopeFor(null, false)).toBe("global");
    expect(scopeFor(undefined, false)).toBe("global");
  });
  it("is global when the running game follows global", () => {
    expect(scopeFor("1245620", true)).toBe("global");
  });
  it("is game when the running game has its own active profile", () => {
    expect(scopeFor("1245620", false)).toBe("game");
    expect(scopeFor("ns:hades", false)).toBe("game");
  });
});
