import { describe, expect, it } from "vitest";
import { activityDebounceMs, ecoBrightness, isDimEcho, isFloorEcho } from "./eco";

describe("ecoBrightness", () => {
  it("is the wake level when active, the floor when idle", () => {
    expect(ecoBrightness(true, 45, 0)).toBe(45);
    expect(ecoBrightness(false, 45, 0)).toBe(0);
  });
});

describe("isDimEcho", () => {
  it("is false when nothing has been driven yet", () => {
    expect(isDimEcho(44, null, 0)).toBe(false);
  });

  it("recognises our own recent write echoing back", () => {
    expect(isDimEcho(44, 44, 100)).toBe(true);
  });

  it("tolerates panel quantisation within a couple percent", () => {
    expect(isDimEcho(43, 44, 100)).toBe(true);
    expect(isDimEcho(47, 44, 100)).toBe(false);
  });

  it("treats a value far from our last write as external (the user)", () => {
    expect(isDimEcho(20, 44, 100)).toBe(false);
  });

  it("stops claiming an echo once the window passes (a later change is the user)", () => {
    expect(isDimEcho(44, 44, 5000)).toBe(false);
  });
});

describe("isFloorEcho", () => {
  it("recognises an echo sitting at the idle floor (our own dim, never the user)", () => {
    expect(isFloorEcho(12, 12)).toBe(true);
    expect(isFloorEcho(13, 12)).toBe(true); // panel quantisation
  });

  it("is false for a real wake level well above the floor", () => {
    expect(isFloorEcho(44, 12)).toBe(false);
  });
});

describe("activityDebounceMs", () => {
  it("wakes fast but debounces idle to swallow flapping", () => {
    expect(activityDebounceMs(true)).toBeLessThan(activityDebounceMs(false));
  });
});
