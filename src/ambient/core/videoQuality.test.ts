import { describe, expect, it } from "vitest";

import { needsCopy, videoTarget } from "./videoQuality";

describe("videoQuality", () => {
  it("maps each level to a size and frame rate", () => {
    expect(videoTarget("fluid", 800)).toEqual({ height: 200, fps: 30 });
    expect(videoTarget("saver", 800)).toEqual({ height: 200, fps: 15 });
    expect(videoTarget("sharp", 800)).toEqual({ height: 800, fps: 30 });
    expect(videoTarget("fluid", 1200)).toEqual({ height: 300, fps: 30 });
    expect(videoTarget("fluid", 400)).toEqual({ height: 144, fps: 30 });
  });

  it("copies every video on the light levels, only oversized ones on sharp", () => {
    expect(needsCopy("sharp", 720, videoTarget("sharp", 800))).toBe(false);
    expect(needsCopy("sharp", 2160, videoTarget("sharp", 800))).toBe(true);
    expect(needsCopy("fluid", 480, videoTarget("fluid", 800))).toBe(true);
  });
});
