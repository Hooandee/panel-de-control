import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GameMediaDirector, SETTLE_MS, ThemeAudio, type GameMedia } from "./gameMedia";

const MEDIA: GameMedia = { trailer: { url: "https://video.akamai.steamstatic.com/a.m3u8", poster: "", title: "" }, theme: null };

describe("GameMediaDirector", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("waits for the selection to settle and drops answers for games already left", async () => {
    const lookup = vi.fn(async () => MEDIA);
    const changed = vi.fn();
    const director = new GameMediaDirector(lookup, changed);
    director.select("1");
    await vi.advanceTimersByTimeAsync(SETTLE_MS / 2);
    director.select("2");
    expect(director.pending()).toBe(true);
    await vi.advanceTimersByTimeAsync(SETTLE_MS + 10);
    expect(director.pending()).toBe(false);
    expect(lookup).toHaveBeenCalledTimes(1);
    expect(director.current()?.appid).toBe("2");
    director.select(null);
    expect(director.current()).toBeNull();
    expect(director.pending()).toBe(false);
    expect(changed).toHaveBeenCalledTimes(2);
  });

  it("remembers what each game had", async () => {
    const lookup = vi.fn(async () => MEDIA);
    const director = new GameMediaDirector(lookup, () => undefined);
    for (const id of ["1", "2", "1"]) {
      director.select(id);
      await vi.advanceTimersByTimeAsync(SETTLE_MS + 10);
    }
    expect(lookup).toHaveBeenCalledTimes(2);
  });

  it("looks up the neighbours only after the selected game settles, so moving next to it needs no lookup", async () => {
    const lookup = vi.fn(async (_appid: string) => MEDIA);
    const director = new GameMediaDirector(lookup, () => undefined, () => ["2", "3"]);
    director.select("1");
    expect(lookup).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(SETTLE_MS + 10);
    expect(lookup.mock.calls.map(([appid]) => appid)).toEqual(["1", "2", "3"]);
    director.select("2");
    await vi.advanceTimersByTimeAsync(SETTLE_MS + 10);
    expect(lookup).toHaveBeenCalledTimes(3);
    expect(director.current()?.appid).toBe("2");
  });

  it("stops looking up neighbours once the selection moves on", async () => {
    let finish: (media: GameMedia) => void = () => undefined;
    const lookup = vi.fn((appid: string) => appid === "2" ? new Promise<GameMedia>((resolve) => { finish = resolve; }) : Promise.resolve(MEDIA));
    const director = new GameMediaDirector(lookup, () => undefined, () => ["2", "3"]);
    director.select("1");
    await vi.advanceTimersByTimeAsync(SETTLE_MS + 10);
    director.select(null);
    finish(MEDIA);
    await vi.advanceTimersByTimeAsync(0);
    expect(lookup.mock.calls.map(([appid]) => appid)).toEqual(["1", "2"]);
  });
});

describe("ThemeAudio", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("fades in, and switching tracks silences the previous one at once", async () => {
    const made: { src: string; volume: number; paused: boolean; loop: boolean; play: () => Promise<void>; pause: () => void; load: () => void; removeAttribute: (n: string) => void; getAttribute: (n: string) => string | null }[] = [];
    const theme = new ThemeAudio(() => {
      const audio = { src: "", volume: 1, paused: true, loop: false, play: async () => { audio.paused = false; }, pause: () => { audio.paused = true; }, load: () => undefined, removeAttribute: () => { audio.src = ""; }, getAttribute: () => audio.src || null };
      made.push(audio);
      return audio as unknown as HTMLAudioElement;
    });
    theme.play("https://a.test/1.m4a", 0.5);
    await vi.advanceTimersByTimeAsync(1000);
    expect(made[0].volume).toBe(0.5);
    theme.play("https://a.test/2.m4a", 0.5);
    expect(made[0].paused).toBe(true);
    theme.stop();
    await vi.advanceTimersByTimeAsync(1000);
    expect(made[1].paused).toBe(true);
    expect(theme.url).toBeNull();
  });
});
