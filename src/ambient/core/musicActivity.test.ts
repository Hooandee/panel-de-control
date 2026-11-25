import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MUSIC_SILENCE_SETTLE_MS, MusicActivity, musicAudible } from "./musicActivity";

describe("musicAudible", () => {
  it.each([
    ["playing", 0.5, true],
    ["playing", 0, false],
    ["paused", 0.5, false],
    ["loading", 0.5, false],
    ["retrying", 0.5, false],
    ["error", 0.5, false],
    ["idle", 0.5, false],
  ])("status %s at volume %s is audible: %s", (status, volume, audible) => {
    expect(musicAudible({ status, volume })).toBe(audible);
  });
});

describe("MusicActivity", () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it("reports playing at once and stopped only once the silence lasts", () => {
    const changes: boolean[] = [];
    const activity = new MusicActivity((playing) => changes.push(playing));
    activity.update(false);
    expect(changes).toEqual([]);
    activity.update(true);
    activity.update(true);
    expect(changes).toEqual([true]);

    activity.update(false);
    vi.advanceTimersByTime(MUSIC_SILENCE_SETTLE_MS - 1);
    activity.update(true);
    vi.advanceTimersByTime(MUSIC_SILENCE_SETTLE_MS);
    expect(changes).toEqual([true]);

    activity.update(false);
    vi.advanceTimersByTime(500);
    activity.update(false);
    vi.advanceTimersByTime(MUSIC_SILENCE_SETTLE_MS - 500);
    expect(changes).toEqual([true, false]);
  });

  it("drops a pending stop when disposed", () => {
    const onChange = vi.fn();
    const activity = new MusicActivity(onChange, 1000);
    activity.update(true);
    activity.update(false);
    activity.dispose();
    vi.advanceTimersByTime(5000);
    expect(onChange).toHaveBeenCalledTimes(1);
  });
});
