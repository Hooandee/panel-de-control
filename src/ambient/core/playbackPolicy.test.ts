import { describe, expect, it } from "vitest";

import { gameVolumeTarget, nextRetryDelay, planForGameState } from "./playbackPolicy";

describe("playback policy", () => {
  it("plays normally outside games", () => {
    expect(planForGameState(false, 0)).toEqual({ playing: true, volumeScale: 1 });
  });

  it("pauses at zero, keeps full as it is and scales in between", () => {
    expect(planForGameState(true, 0).playing).toBe(false);
    expect(planForGameState(true, 100)).toEqual({ playing: true, volumeScale: 1 });
    expect(planForGameState(true, 30)).toEqual({ playing: true, volumeScale: 0.3 });
  });

  it("lowers the game only while Ambiente's media sounds", () => {
    expect(gameVolumeTarget(false, true, 40, false)).toBeNull();
    expect(gameVolumeTarget(true, true, 40, false)).toBe(40);
    expect(gameVolumeTarget(true, false, 40, true)).toBe(100);
  });

  it("never touches a game Panel did not lower", () => {
    expect(gameVolumeTarget(true, false, 40, false)).toBeNull();
    expect(gameVolumeTarget(true, true, 100, false)).toBeNull();
    expect(gameVolumeTarget(true, true, 100, true)).toBe(100);
  });

  it("radio retries three times then gives up", () => {
    expect([0, 1, 2, 3].map(nextRetryDelay)).toEqual([2000, 5000, 10000, null]);
  });
});
