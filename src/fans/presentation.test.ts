import { describe, expect, it } from "vitest";

import { desktopFanVisible } from "./presentation";

describe("desktop fan presentation", () => {
  it("hides only the unverified Steam Machine GPU channel", () => {
    expect(desktopFanVisible("steam_machine", "gpu")).toBe(false);
    expect(desktopFanVisible("steam_machine", "system")).toBe(true);
    expect(desktopFanVisible("generic", "gpu")).toBe(true);
    expect(desktopFanVisible(undefined, undefined)).toBe(true);
  });
});
