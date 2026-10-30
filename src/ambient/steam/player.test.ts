// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AmbientPlayer, type Track } from "./player";

const radio: Track = { id: "r1", title: "Lofi", subtitle: "FR", art: "", url: "https://s.test/lofi", live: true };
const songs: Track[] = [
  { id: "a", title: "A", subtitle: "", art: "", url: "http://127.0.0.1/a.mp3", live: false },
  { id: "b", title: "B", subtitle: "", art: "", url: "http://127.0.0.1/b.mp3", live: false },
];

function fakeAudio() {
  const audio = document.createElement("audio");
  vi.spyOn(audio, "play").mockResolvedValue(undefined);
  vi.spyOn(audio, "pause").mockImplementation(() => audio.dispatchEvent(new Event("pause")));
  vi.spyOn(audio, "load").mockImplementation(() => undefined);
  return audio;
}

describe("AmbientPlayer", () => {
  let audio: HTMLAudioElement;
  let player: AmbientPlayer;
  const errors: string[] = [];

  beforeEach(() => {
    vi.useFakeTimers();
    audio = fakeAudio();
    errors.length = 0;
    player = new AmbientPlayer(() => audio, (d) => errors.push(d));
  });

  afterEach(() => {
    player.dispose();
    vi.useRealTimers();
  });

  it("follows the repeat mode when a track ends", () => {
    player.playQueue(songs, 1);
    audio.dispatchEvent(new Event("ended"));
    expect(player.getSnapshot().track?.id).toBe("a");
    player.setRepeat("one");
    audio.dispatchEvent(new Event("ended"));
    expect(player.getSnapshot().track?.id).toBe("a");
    player.next();
    expect(player.getSnapshot().track?.id).toBe("b");
    player.setRepeat("off");
    audio.dispatchEvent(new Event("ended"));
    expect(player.getSnapshot()).toMatchObject({ status: "paused", track: { id: "b" }, position: 0 });
    expect(player.isPlaying).toBe(false);
  });

  it("starts the first link added to an empty player and only queues the rest", () => {
    player.enqueue([songs[0]]);
    expect(player.getSnapshot()).toMatchObject({ status: "loading", track: { id: "a" } });
    player.enqueue([songs[1], radio]);
    expect(player.getSnapshot().track?.id).toBe("a");
    expect(player.getSnapshot().queue.map((q) => q.track.id)).toEqual(["a", "b", "r1"]);
  });

  it("removing the playing entry plays what follows; moving keeps the current one", () => {
    player.playQueue([...songs, radio]);
    const [first, , third] = player.getSnapshot().queue;
    player.moveEntry(third.key, 0);
    expect(player.getSnapshot()).toMatchObject({ queueIndex: 1, track: { id: "a" } });
    player.removeEntry(first.key);
    expect(player.getSnapshot().track?.id).toBe("b");
    expect(player.getSnapshot().queue.map((q) => q.track.id)).toEqual(["r1", "b"]);
    player.playEntry(player.getSnapshot().queue[0].key);
    expect(player.getSnapshot().track?.id).toBe("r1");
  });

  it("removing the paused current entry and pressing play plays the one that took its place", () => {
    player.playQueue(songs);
    player.pause();
    player.removeEntry(player.getSnapshot().queue[0].key);
    player.resume();
    expect(player.getSnapshot().track?.id).toBe("b");
    expect(audio.getAttribute("src")).toBe("http://127.0.0.1/b.mp3");
  });

  it("clearing keeps only what is playing", () => {
    player.playQueue(songs, 1);
    player.clearQueue();
    expect(player.getSnapshot().queue.map((q) => q.track.id)).toEqual(["b"]);
  });

  it("reports playing only when the element says so", () => {
    player.playQueue([radio]);
    expect(player.getSnapshot().status).toBe("loading");
    audio.dispatchEvent(new Event("playing"));
    expect(player.getSnapshot()).toMatchObject({ status: "playing", track: { id: "r1" } });
  });

  it("restores a paused checkpoint without playing or loading it until resume", () => {
    player.playQueue(songs, 1);
    audio.currentTime = 42;
    player.setVolume(0.7);
    player.pause();
    const saved = player.checkpoint();
    player.playQueue([radio]);
    player.setVolume(0.2);
    vi.mocked(audio.play).mockClear();
    player.restore(saved);
    expect(audio.play).not.toHaveBeenCalled();
    expect(audio.getAttribute("src")).toBeNull();
    expect(player.getSnapshot()).toMatchObject({ status: "paused", track: { id: "b" }, position: 42, volume: 0.7 });
    expect(player.position()).toBe(42);
    player.resume();
    audio.dispatchEvent(new Event("loadedmetadata"));
    expect(audio.play).toHaveBeenCalledOnce();
    expect(audio.currentTime).toBe(42);
    player.next();
    expect(player.getSnapshot().track?.id).toBe("a");
  });

  it("restores idle after a preview and never revives it from a stale metadata event", () => {
    const saved = player.checkpoint();
    player.playQueue(songs, 0, 20);
    player.restore(saved);
    audio.currentTime = 0;
    audio.dispatchEvent(new Event("loadedmetadata"));
    expect(audio.currentTime).toBe(0);
    expect(player.getSnapshot()).toMatchObject({ status: "idle", track: null, position: 0 });
    expect(player.isPlaying).toBe(false);
  });

  it("restores the original playing queue and silences a video preview first", () => {
    const video = Object.assign(fakeAudio(), { nextVideo: vi.fn(), previousVideo: vi.fn(), dispose: vi.fn(), setBounds: vi.fn(), setVisible: vi.fn() });
    const shared = new AmbientPlayer(() => audio, vi.fn(), undefined, () => video);
    try {
      shared.playQueue(songs, 1);
      audio.currentTime = 32;
      shared.setVolume(0.8);
      const checkpoint = shared.checkpoint();
      shared.playQueue([{ ...songs[0], id: "preview", kind: "video" }], 0, 0, true);
      expect(audio.getAttribute("src")).toBeNull();
      expect(shared.getSnapshot().video).toBe(true);
      vi.mocked(audio.play).mockImplementation(async () => {
        expect(video.getAttribute("src")).toBeNull();
      });
      shared.restore(checkpoint);
      audio.dispatchEvent(new Event("loadedmetadata"));
      expect(shared.getSnapshot()).toMatchObject({ track: { id: "b" }, video: false, volume: 0.8 });
      expect(shared.isPlaying).toBe(true);
      expect(audio.currentTime).toBe(32);
      shared.next();
      expect(shared.getSnapshot().track?.id).toBe("a");
    } finally { shared.dispose(); }
  });

  it("radio retries three times then reports an error", () => {
    player.playQueue([radio]);
    for (const delay of [2000, 5000, 10000]) {
      audio.dispatchEvent(new Event("error"));
      expect(player.getSnapshot().status).toBe("retrying");
      vi.advanceTimersByTime(delay);
    }
    audio.dispatchEvent(new Event("error"));
    expect(player.getSnapshot().status).toBe("error");
    expect(errors).toEqual(["radio:media_error_0"]);
  });

  it("reports an offline Twitch channel at once instead of retrying it", () => {
    const video = Object.assign(fakeAudio(), { nextVideo: vi.fn(), previousVideo: vi.fn(), dispose: vi.fn(), setBounds: vi.fn(), setVisible: vi.fn() });
    const twitch = new AmbientPlayer(() => audio, (d) => errors.push(d), undefined, () => video);
    twitch.playQueue([{ ...radio, url: "https://www.twitch.tv/somechannel" }]);
    Object.defineProperty(video, "error", { value: { code: 100 } });
    video.dispatchEvent(new Event("error"));
    expect(twitch.getSnapshot()).toMatchObject({ status: "error", error: "media_error_100" });
    twitch.dispose();
  });

  it("a successful play resets the retry budget", () => {
    player.playQueue([radio]);
    audio.dispatchEvent(new Event("error"));
    vi.advanceTimersByTime(2000);
    audio.dispatchEvent(new Event("playing"));
    audio.dispatchEvent(new Event("error"));
    vi.advanceTimersByTime(2000);
    expect(player.getSnapshot().status).toBe("loading");
  });

  it("music advances on end and wraps", () => {
    player.playQueue(songs);
    audio.dispatchEvent(new Event("ended"));
    expect(player.getSnapshot().track?.id).toBe("b");
    audio.dispatchEvent(new Event("ended"));
    expect(player.getSnapshot().track?.id).toBe("a");
  });

  it("pause is reported and volume is scaled for ducking", () => {
    player.playQueue(songs);
    player.setVolume(0.8);
    player.setScale(0.5);
    expect(audio.volume).toBeCloseTo(0.4);
    player.pause();
    expect(player.getSnapshot().status).toBe("paused");
    expect(player.isPlaying).toBe(false);
  });

  it("never plays again once disposed", () => {
    player.dispose();
    player.playQueue(songs);
    expect(audio.play).not.toHaveBeenCalled();
  });

  it("reports real position and duration at most once a second", () => {
    player.playQueue(songs);
    Object.defineProperty(audio, "duration", { value: 200, configurable: true });
    audio.currentTime = 42;
    vi.setSystemTime(10_000);
    audio.dispatchEvent(new Event("timeupdate"));
    expect(player.getSnapshot()).toMatchObject({ position: 42, duration: 200 });
    audio.currentTime = 43;
    audio.dispatchEvent(new Event("timeupdate"));
    expect(player.getSnapshot().position).toBe(42);
  });

  describe("YouTube", () => {
    const mix: Track = { id: "y", title: "Link", subtitle: "", art: "", url: "https://www.youtube.com/watch?v=dsuJZx24V_A&list=RDdsuJZx24V_A", live: false };

    function fakeYouTube() {
      const engine = Object.assign(document.createElement("audio"), { nextVideo: vi.fn(), previousVideo: vi.fn(), dispose: vi.fn() });
      vi.spyOn(engine, "play").mockResolvedValue(undefined);
      vi.spyOn(engine, "pause").mockImplementation(() => undefined);
      vi.spyOn(engine, "load").mockImplementation(() => undefined);
      return engine;
    }

    it("replaces the radio, takes the video title and steps through the list", () => {
      const engine = fakeYouTube();
      const yt = new AmbientPlayer(() => audio, (d) => errors.push(d), () => engine);
      yt.playQueue([radio]);
      audio.dispatchEvent(new Event("playing"));
      yt.playQueue([mix]);
      expect(audio.pause).toHaveBeenCalled();
      audio.dispatchEvent(new Event("playing"));
      expect(yt.getSnapshot().status).toBe("loading");
      engine.dispatchEvent(new Event("playing"));
      engine.dispatchEvent(new CustomEvent("trackinfo", { detail: { title: "Life Will Change", art: "https://i.ytimg.com/vi/dsuJZx24V_A/hqdefault.jpg" } }));
      expect(yt.getSnapshot()).toMatchObject({ status: "playing", track: { id: "y", title: "Life Will Change" } });
      yt.next();
      expect(engine.nextVideo).toHaveBeenCalledOnce();
      yt.dispose();
      expect(engine.dispose).toHaveBeenCalled();
    });
  });

  it("seeks inside songs and never past their end, but not in live radio", () => {
    player.playQueue(songs);
    audio.dispatchEvent(new Event("playing"));
    Object.defineProperty(audio, "duration", { configurable: true, get: () => 100 });
    audio.dispatchEvent(new Event("timeupdate"));
    player.seekTo(40);
    expect(audio.currentTime).toBe(40);
    player.seekTo(500);
    expect(audio.currentTime).toBe(99);
    player.playQueue([radio]);
    audio.currentTime = 0;
    player.seekTo(30);
    expect(audio.currentTime).toBe(0);
  });
});


describe("local video capability", () => {
  it("uses the video engine for scanned videos with opaque media-server URLs", () => {
    const audio = fakeAudio();
    const video = Object.assign(fakeAudio(), { nextVideo: vi.fn(), previousVideo: vi.fn(), dispose: vi.fn(), setBounds: vi.fn(), setVisible: vi.fn() });
    const player = new AmbientPlayer(() => audio, vi.fn(), undefined, () => video);
    try {
      player.setVideoMode(true);
      player.playQueue([{ id: "local:video", title: "Video", subtitle: "", art: "", url: "http://127.0.0.1:8080/m/token/local%3Avideo", live: false, kind: "video" }]);
      expect(player.canShowVideo()).toBe(true);
      expect(player.getSnapshot().video).toBe(true);
      expect(video.play).toHaveBeenCalledTimes(1);
      expect(audio.play).not.toHaveBeenCalled();
    } finally { player.dispose(); }
  });
});
