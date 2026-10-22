import { describe, expect, it } from "vitest";

import { blankFrame, decodeFrame, encodeFrame, fill, getPixel, paint } from "./drawing";

describe("drawing", () => {
  it("paints a pixel and mirrors it across the middle", () => {
    const frame = blankFrame();
    paint(frame, 3, 4, [255, 0, 0], true);
    expect(getPixel(frame, 3, 4)).toEqual([255, 0, 0]);
    expect(getPixel(frame, 60, 4)).toEqual([255, 0, 0]);
    expect(getPixel(frame, 4, 4)).toEqual([0, 0, 0]);
  });

  it("flood fills only the touching region", () => {
    const frame = blankFrame();
    for (let y = 0; y < 54; y += 1) paint(frame, 10, y, [9, 9, 9], false);
    fill(frame, 2, 2, [0, 255, 0]);
    expect(getPixel(frame, 0, 53)).toEqual([0, 255, 0]);
    expect(getPixel(frame, 10, 20)).toEqual([9, 9, 9]);
    expect(getPixel(frame, 30, 30)).toEqual([0, 0, 0]);
  });

  it("filling with the same colour is a no-op", () => {
    const frame = blankFrame();
    fill(frame, 0, 0, [0, 0, 0]);
    expect(getPixel(frame, 5, 5)).toEqual([0, 0, 0]);
  });

  it("round-trips through base64", () => {
    const frame = blankFrame();
    paint(frame, 63, 53, [1, 2, 3], false);
    expect(Array.from(decodeFrame(encodeFrame(frame)))).toEqual(Array.from(frame));
    expect(atob(encodeFrame(frame)).length).toBe(64 * 54 * 3);
  });

  it("ignores pixels outside the canvas", () => {
    const frame = blankFrame();
    paint(frame, -1, 0, [1, 1, 1], false);
    paint(frame, 64, 0, [1, 1, 1], false);
    expect(frame.every((v) => v === 0)).toBe(true);
  });
});
