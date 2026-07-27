import { describe, it, expect } from "vitest";
import { effectiveEnabled, moduleState, countStates } from "./moduleLogic";

const S = (...ids: string[]) => new Set(ids);

describe("effectiveEnabled", () => {
  it("tab enabled by default", () => {
    expect(effectiveEnabled("fans", S())).toBe(true);
  });
  it("user-disabled tab is off", () => {
    expect(effectiveEnabled("fans", S("fans"))).toBe(false);
  });
  it("autoTdp cascades from power", () => {
    expect(effectiveEnabled("autoTdp", S("power"))).toBe(false);
    expect(effectiveEnabled("autoTdp", S())).toBe(true);
  });
  it("fanControl cascades from fans", () => {
    expect(effectiveEnabled("fanControl", S("fans"))).toBe(false);
  });
  it("learning needs power OR fans", () => {
    expect(effectiveEnabled("learning", S("power", "fans"))).toBe(false);
    expect(effectiveEnabled("learning", S("fans"))).toBe(true);
    expect(effectiveEnabled("learning", S())).toBe(true);
  });
});

describe("moduleState", () => {
  it("locked wins", () => {
    expect(moduleState("settings", S("settings"), false, true)).toBe("locked");
  });
  it("user-disabled", () => {
    expect(moduleState("fans", S("fans"), false, false)).toBe("disabled");
  });
  it("blocked = dep unmet, not user-disabled", () => {
    expect(moduleState("learning", S("power", "fans"), false, false)).toBe("blocked");
  });
  it("hidden but enabled = background", () => {
    expect(moduleState("power", S(), true, false)).toBe("background");
  });
  it("plain visible", () => {
    expect(moduleState("power", S(), false, false)).toBe("visible");
  });
});

describe("countStates", () => {
  it("counts visible/background/disabled", () => {
    const c = countStates(
      [
        { id: "power", hidden: false },
        { id: "fans", hidden: true },
        { id: "display", hidden: false },
      ],
      S("display"),
    );
    expect(c).toEqual({ visible: 1, background: 1, disabled: 1, blocked: 0 });
  });
});
