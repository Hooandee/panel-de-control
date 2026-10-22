import { describe, expect, it } from "vitest";

import { decodeFrames, frameAt, PANEL_H, PANEL_W } from "./pixelFrames";

describe("pixel frames", () => {
  it("decodes base64 index frames and centisecond delays", () => {
    const raw = new Uint8Array(PANEL_W * PANEL_H);
    raw[5] = 2;
    const b64 = btoa(String.fromCharCode(...raw));
    const decoded = decodeFrames({ palette: [[0, 0, 0], [1, 2, 3], [9, 9, 9]], frames: [b64], delays: [6000], firmwareAnimation: null });
    expect(decoded.frames[0].length).toBe(PANEL_W * PANEL_H);
    expect(decoded.frames[0][5]).toBe(2);
    expect(decoded.delaysMs).toEqual([60000]);
  });

  it("never shows a frame faster than the panel can", () => {
    expect(decodeFrames({ palette: [], frames: [], delays: [1, 0], firmwareAnimation: null }).delaysMs).toEqual([60, 60]);
  });

  it("finds the frame for an elapsed time and loops", () => {
    expect(frameAt([100, 200, 300], 0)).toBe(0);
    expect(frameAt([100, 200, 300], 150)).toBe(1);
    expect(frameAt([100, 200, 300], 599)).toBe(2);
    expect(frameAt([100, 200, 300], 650)).toBe(0);
    expect(frameAt([], 50)).toBe(0);
  });
});
