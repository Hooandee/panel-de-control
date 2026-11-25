import { describe, expect, it } from "vitest";

import { fullscreenVideoBounds, cardWidth, clampPosition, cornerPosition, nearestCorner, springStep } from "./overlayLayout";

const viewport = { width: 924, height: 577 };

describe("floating card geometry", () => {
  it("is the mini player alone or wide enough for the video", () => {
    expect(cardWidth(viewport, 0, false, 52)).toBe(280);
    expect(cardWidth(viewport, 0, true, 40)).toBe(370);
    expect(cardWidth(viewport, 600, true, 52)).toBe(924 - 600 - 32);
  });

  it("sits in its corner, clear of the QAM on the right", () => {
    const card = { width: 280, height: 80 };
    expect(cornerPosition("top-left", card, viewport, 0)).toEqual({ x: 16, y: 16 });
    expect(cornerPosition("bottom-right", card, viewport, 351)).toEqual({ x: 924 - 351 - 16 - 280, y: 577 - 16 - 80 });
  });

  it("snaps to the corner nearest the drop point", () => {
    const card = { width: 280, height: 80 };
    expect(nearestCorner({ x: 600, y: 400 }, card, viewport, 0)).toBe("bottom-right");
    expect(nearestCorner({ x: 40, y: 30 }, card, viewport, 0)).toBe("top-left");
    expect(nearestCorner({ x: 300, y: 30 }, card, viewport, 351)).toBe("top-right");
  });

  it("never leaves the screen while dragged", () => {
    expect(clampPosition({ x: -40, y: 900 }, { width: 280, height: 80 }, viewport)).toEqual({ x: 0, y: 497 });
  });

  it("approaches the target and stops", () => {
    let point: { x: number; y: number } | null = { x: 0, y: 0 };
    let frames = 0;
    while (point && frames < 100) {
      point = springStep(point, { x: 100, y: 50 });
      frames += 1;
    }
    expect(point).toBeNull();
    expect(frames).toBeLessThan(40);
  });
});

it("fits video inside a full Deck screen without cropping or stretching", () => {
  expect(fullscreenVideoBounds({ width: 1280, height: 800 })).toEqual({ x: 0, y: 40, width: 1280, height: 720 });
  expect(fullscreenVideoBounds({ width: 800, height: 1280 })).toEqual({ x: 0, y: 415, width: 800, height: 450 });
});
