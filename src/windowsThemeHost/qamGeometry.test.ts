// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";

import { applyQamGeometry, measureQamGeometry } from "./qamGeometry";

const frame = (screenX: number, screenY: number, innerWidth: number, innerHeight: number, devicePixelRatio = 1.42) =>
  ({ screenX, screenY, innerWidth, innerHeight, devicePixelRatio });

describe("quick access geometry", () => {
  it("measures the visible panel of Steam's Windows quick access window (Ally X, 1080p)", () => {
    // The window is 853 px wide but runs off the right edge: only 348 px of it are on screen.
    expect(measureQamGeometry(frame(1005, 40, 853, 680), frame(0, 0, 1353, 761))).toEqual({ width: 348, top: 40, bottom: 41 });
  });

  it("ignores a hidden or off-screen window", () => {
    expect(measureQamGeometry(frame(0, 0, 0, 0), frame(0, 0, 1353, 761))).toBeNull();
    expect(measureQamGeometry(frame(1400, 40, 853, 680), frame(0, 0, 1353, 761))).toBeNull();
  });

  it("publishes the geometry on Big Picture and removes it", () => {
    applyQamGeometry(document, { width: 348, top: 40, bottom: 41 });
    const style = document.documentElement.style;
    expect([style.getPropertyValue("--pdc-host-qam-width"), style.getPropertyValue("--pdc-host-qam-top"), style.getPropertyValue("--pdc-host-qam-bottom")])
      .toEqual(["348px", "40px", "41px"]);
    applyQamGeometry(document, null);
    expect(style.getPropertyValue("--pdc-host-qam-width")).toBe("");
  });
});
