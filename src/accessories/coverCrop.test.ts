import { describe, expect, it } from "vitest";

import { coverCrop } from "./pixelFrames";

describe("cover crop", () => {
  it("crops the sides of a wide hero image", () => {
    const crop = coverCrop(3840, 1240);
    expect(crop.sh).toBe(1240);
    expect(crop.sw / crop.sh).toBeCloseTo(64 / 54);
    expect(crop.sx).toBeCloseTo((3840 - crop.sw) / 2);
  });

  it("crops top and bottom of a tall capsule", () => {
    const crop = coverCrop(600, 900);
    expect(crop.sw).toBe(600);
    expect(crop.sw / crop.sh).toBeCloseTo(64 / 54);
    expect(crop.sy).toBeCloseTo((900 - crop.sh) / 2);
  });
});

describe("portrait crop", () => {
  it("fits a capsule into the side column", () => {
    const crop = coverCrop(600, 900, 36, 54);
    expect(crop.sw / crop.sh).toBeCloseTo(36 / 54);
  });
});
