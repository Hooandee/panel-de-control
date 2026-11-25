import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const html = readFileSync(new URL("../py_modules/ambient/adapters/video_page.html", import.meta.url), "utf8");
const script = html.match(/<script>([\s\S]*?)<\/script>/)![1];
const ORIGIN = "https://player.vimeo.com";

function page(provider = "vimeo") {
  const listeners: Array<(event: { data: unknown; origin: string; source: unknown }) => void> = [];
  const frame = { src: "", style: { cssText: "" }, allow: "", onload: () => {}, contentWindow: { postMessage: vi.fn() } };
  const reports: Array<{ s: string; t: number; d: number; err: number }> = [];
  const window = {
    parent: { postMessage: ({ pdc }: { pdc: typeof reports[number] }) => reports.push({ ...pdc }) },
    addEventListener: (_type: string, listener: typeof listeners[number]) => listeners.push(listener),
    pdc: undefined as unknown as { play(): void; pause(): void; seek(value: number): void; volume(value: number): void },
  };
  runInNewContext(script, {
    window, document: { createElement: () => frame, getElementById: () => ({ replaceWith() {} }) },
    location: { search: `?embed=${provider}&ref=76979871&k=test&vol=60` },
    URLSearchParams, setInterval, setTimeout, clearTimeout,
  });
  const emit = (data: unknown, origin = ORIGIN, source: unknown = frame.contentWindow) => listeners.forEach((listener) => listener({ data, origin, source }));
  const commands = (method: string) => frame.contentWindow.postMessage.mock.calls.map(([data]) => JSON.parse(data)).filter((data) => data.method === method);
  const state = () => { vi.advanceTimersByTime(500); return reports[reports.length - 1]; };
  return { frame, emit, commands, state, api: window.pdc };
}

describe("served Vimeo player page", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("does not report playback from iframe load, a play command, or the provider's play intent", () => {
    const p = page();
    p.frame.onload();
    expect(p.state().s).toBe("loading");
    p.api.play();
    p.emit({ event: "play" });
    expect(p.state().s).toBe("loading");
    p.emit({ event: "ready" });
    expect(p.commands("addEventListener").map((command) => command.value)).toEqual(expect.arrayContaining(["playing", "pause", "ended", "timeupdate", "durationchange", "error"]));
    p.emit({ event: "playing" });
    expect(p.state().s).toBe("playing");
  });

  it.each(["ready", "ping"])("completes the %s handshake only once and starts at the requested volume", (handshake) => {
    const p = page();
    p.frame.onload();
    expect(p.commands("ping")).toHaveLength(1);
    const message = handshake === "ready" ? { event: "ready" } : { method: "ping", value: true };
    p.emit(message);
    p.emit(message);
    expect(p.commands("setVolume")).toEqual([{ method: "setVolume", value: 0.6 }]);
    expect(p.commands("play")).toHaveLength(1);
  });

  it("reports provider time, duration, pause, completion and error without inventing progress", () => {
    const p = page();
    p.emit({ event: "ready" });
    p.emit({ event: "playing" });
    p.emit(JSON.stringify({ event: "timeupdate", data: { seconds: 12.5, duration: 98 } }));
    expect(p.state()).toMatchObject({ s: "playing", t: 12.5, d: 98, err: 0 });
    p.emit({ event: "durationchange", data: { duration: 100 } });
    expect(p.state().d).toBe(100);
    p.emit({ event: "pause" });
    expect(p.state().s).toBe("paused");
    p.emit({ event: "ended" });
    expect(p.state().s).toBe("ended");
    p.emit({ event: "error", data: { name: "UnsupportedError", message: "Cannot play" } });
    expect(p.state()).toMatchObject({ s: "error", err: 0 });
  });

  it("rejects the wrong origin, another Vimeo iframe and malformed messages", () => {
    const p = page();
    p.emit({ event: "playing" }, "https://other.test");
    p.emit({ event: "playing" }, ORIGIN, {});
    p.emit("not JSON");
    p.emit(null);
    expect(p.state().s).toBe("loading");
    p.emit({ event: "ready" });
    p.emit({ event: "timeupdate", data: { seconds: "12", duration: Infinity } });
    expect(p.state()).toMatchObject({ t: 0, d: 0 });
  });

  it("times out silently stalled playback as a generic error despite continuing page heartbeats", () => {
    const p = page();
    p.emit({ event: "ready" });
    p.emit({ event: "play" });
    vi.advanceTimersByTime(21000);
    expect(p.state()).toMatchObject({ s: "error", err: 0 });
    expect(p.commands("play")).toHaveLength(1);
  });

  it("confirms advancing time when the handshake missed the first playing event", () => {
    const p = page();
    p.frame.onload();
    p.emit({ method: "ping", value: true });
    p.emit({ event: "timeupdate", data: { seconds: 12, duration: 100 } });
    expect(p.state().s).toBe("loading");
    p.emit({ event: "timeupdate", data: { seconds: 12.5, duration: 100 } });
    expect(p.state()).toMatchObject({ s: "playing", t: 12.5 });
    vi.advanceTimersByTime(21000);
    expect(p.state().s).toBe("playing");
  });

  it("does not infer playback from an unpaused flag, stationary time or a seek jump", () => {
    const p = page();
    p.emit({ event: "ready" });
    p.emit({ method: "getPaused", value: false });
    p.emit({ event: "timeupdate", data: { seconds: 0, duration: 100 } });
    p.emit({ event: "timeupdate", data: { seconds: 0, duration: 100 } });
    p.api.seek(40);
    p.emit({ event: "timeupdate", data: { seconds: 40, duration: 100 } });
    expect(p.state().s).toBe("loading");
    vi.advanceTimersByTime(21000);
    expect(p.state()).toMatchObject({ s: "error", err: 0 });
  });

  it("ignores progress jumps during a native seek and requires advancing samples afterwards", () => {
    const p = page();
    p.emit({ event: "ready" });
    p.emit({ event: "timeupdate", data: { seconds: 0, duration: 100 } });
    p.emit({ event: "seeking" });
    p.emit({ event: "timeupdate", data: { seconds: 40, duration: 100 } });
    p.emit({ event: "timeupdate", data: { seconds: 60, duration: 100 } });
    expect(p.state().s).toBe("loading");
    p.emit({ event: "seeked" });
    p.emit({ event: "timeupdate", data: { seconds: 60, duration: 100 } });
    expect(p.state().s).toBe("loading");
    p.emit({ event: "timeupdate", data: { seconds: 60.5, duration: 100 } });
    expect(p.state().s).toBe("playing");
  });

  it.each(["pause", "ended", "error"])("does not revive %s from delayed progress", (event) => {
    const p = page();
    p.emit({ event: "ready" });
    p.emit({ event: "timeupdate", data: { seconds: 12, duration: 100 } });
    p.emit({ event });
    p.emit({ event: "timeupdate", data: { seconds: 12.5, duration: 100 } });
    p.emit({ event: "timeupdate", data: { seconds: 13, duration: 100 } });
    expect(p.state().s).toBe(event === "pause" ? "paused" : event);
  });

  it("requires new progress evidence after an explicit pause and resume", () => {
    const p = page();
    p.emit({ event: "ready" });
    p.emit({ event: "timeupdate", data: { seconds: 12, duration: 100 } });
    p.api.pause();
    p.emit({ event: "timeupdate", data: { seconds: 12.5, duration: 100 } });
    expect(p.state().s).toBe("paused");
    p.api.play();
    p.emit({ event: "timeupdate", data: { seconds: 13, duration: 100 } });
    expect(p.state().s).toBe("loading");
    p.emit({ event: "timeupdate", data: { seconds: 13.5, duration: 100 } });
    expect(p.state().s).toBe("playing");
  });

  it("bounds buffering without repeated waiting events extending the deadline", () => {
    const p = page();
    p.emit({ event: "ready" });
    p.emit({ event: "playing" });
    p.emit({ event: "bufferstart" });
    vi.advanceTimersByTime(15000);
    p.emit({ event: "bufferstart" });
    vi.advanceTimersByTime(6000);
    expect(p.state()).toMatchObject({ s: "error", err: 0 });
  });

  it("accepts a confirmed native-player resume after a provider pause", () => {
    const p = page();
    p.emit({ event: "ready" });
    p.emit({ event: "playing" });
    p.emit({ event: "pause" });
    p.emit({ event: "playing" });
    expect(p.state().s).toBe("playing");
    expect(p.commands("pause")).toHaveLength(0);
  });

  it("cancels loading on explicit pause and permits one user retry after a failure", () => {
    const p = page();
    p.emit({ event: "ready" });
    p.api.pause();
    vi.advanceTimersByTime(21000);
    expect(p.state().s).toBe("paused");
    p.api.play();
    vi.advanceTimersByTime(21000);
    expect(p.state()).toMatchObject({ s: "error", err: 0 });
    p.api.play();
    p.emit({ event: "playing" });
    expect(p.state()).toMatchObject({ s: "playing", err: 0 });
    expect(p.commands("play")).toHaveLength(3);
  });

  it("preserves an error received before ready and does not restart automatically", () => {
    const p = page();
    p.emit({ event: "error", data: { message: "Unsupported playback" } });
    p.frame.onload();
    p.emit({ event: "ready" });
    p.emit({ event: "playing" });
    expect(p.state()).toMatchObject({ s: "error", err: 0 });
    expect(p.commands("play")).toHaveLength(0);
  });

  it("keeps a pre-ready pause through the handshake and resumes once without retry loops", () => {
    const p = page();
    p.api.pause();
    p.emit({ event: "ready" });
    vi.advanceTimersByTime(21000);
    expect(p.state().s).toBe("paused");
    expect(p.commands("play")).toHaveLength(0);
    p.api.play();
    expect(p.state().s).toBe("loading");
    p.emit({ event: "playing" });
    vi.advanceTimersByTime(21000);
    expect(p.state().s).toBe("playing");
    expect(p.commands("play")).toHaveLength(1);
    p.api.pause();
    p.emit({ event: "playing" });
    expect(p.state().s).toBe("paused");
  });

  it.each(["kick", "dailymotion"])("preserves the existing %s iframe controls", (provider) => {
    const p = page(provider);
    p.frame.onload();
    expect(p.state().s).toBe("playing");
    p.api.pause();
    expect(p.frame.src).toBe("about:blank");
    p.api.play();
    expect(p.state().s).toBe("loading");
    expect(p.frame.src).not.toBe("about:blank");
  });
});

describe("served Vimeo player page with legacy events", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("reads progress and completion from playProgress and finish", () => {
    const p = page();
    p.emit({ event: "ready" });
    p.emit({ event: "playProgress", data: { seconds: 10, duration: 185 } });
    p.emit({ event: "playProgress", data: { seconds: 10.3, duration: 185 } });
    expect(p.state()).toMatchObject({ s: "playing", t: 10.3, d: 185 });
    p.emit({ event: "finish" });
    expect(p.state().s).toBe("ended");
  });
});

describe("served Twitch player page", () => {
  it("names Steam's window as a parent so Twitch allows the nested frame", () => {
    const players: Array<Record<string, unknown>> = [];
    const tag: { src: string; onload: () => void } = { src: "", onload: () => {} };
    class Player { constructor(_id: string, options: Record<string, unknown>) { players.push(options); } addEventListener() {} }
    runInNewContext(script, {
      window: { parent: { postMessage() {} }, addEventListener() {} },
      document: { createElement: () => tag, getElementById: () => ({ replaceWith() {} }), head: { appendChild() {} }, body: { appendChild() {} } },
      location: { search: "?embed=twitch&ref=monstercat&k=test&vol=60", hostname: "localhost" },
      URLSearchParams, setInterval, setTimeout, clearTimeout,
      Twitch: { Player: Object.assign(Player, { READY: "ready", PLAYING: "playing", PAUSE: "pause", ENDED: "ended", OFFLINE: "offline" }) },
    });
    tag.onload();
    expect(players[0].parent).toEqual(["localhost", "steamloopback.host"]);
  });

  it("drops the session token from the address the embedded player can read", () => {
    const replaced: string[] = [];
    const tag: { src: string; onload: () => void } = { src: "", onload: () => {} };
    runInNewContext(script, {
      window: { parent: { postMessage() {} }, addEventListener() {} },
      document: { createElement: () => tag, getElementById: () => ({ replaceWith() {} }), head: { appendChild() {} }, body: { appendChild() {} } },
      location: { search: "?embed=twitch&ref=monstercat&k=test&vol=60", hostname: "localhost", pathname: "/v/SECRETTOKEN/player.html" },
      history: { replaceState: (_state: unknown, _title: string, url: string) => replaced.push(url) },
      URLSearchParams, setInterval, setTimeout, clearTimeout,
    });
    expect(replaced).toEqual(["/v/-/player.html"]);
  });
});

describe("served direct stream page", () => {
  function stream(videoWidth: number) {
    const listeners: Record<string, Array<() => void>> = {};
    const video = {
      videoWidth, paused: true, currentTime: 0, duration: 0, volume: 1, error: null, style: { cssText: "" },
      canPlayType: () => "maybe", setAttribute() {}, play: () => Promise.resolve(), pause() {}, load() {},
      addEventListener: (type: string, listener: () => void) => { (listeners[type] ??= []).push(listener); },
    };
    const reports: Array<{ pic: number }> = [];
    let report = () => {};
    runInNewContext(script, {
      window: { parent: { postMessage: ({ pdc }: { pdc: { pic: number } }) => reports.push({ ...pdc }) }, addEventListener() {} },
      document: { createElement: () => video, getElementById: () => ({ replaceWith() {} }), head: { appendChild() {} }, body: { appendChild() {} } },
      location: { search: "?src=https%3A%2F%2Fradio.test%2Flive.mp4&k=test&vol=60" },
      URLSearchParams, setInterval: (fn: () => void) => { report = fn; return 0; }, setTimeout, clearTimeout,
    });
    const fire = (type: string) => listeners[type]?.forEach((listener) => listener());
    return { fire, picture: () => { report(); return reports[reports.length - 1].pic; } };
  }

  it("reports a stream with no picture once its metadata arrives", () => {
    const radio = stream(0);
    expect(radio.picture()).toBe(1);
    radio.fire("loadedmetadata");
    expect(radio.picture()).toBe(0);
  });

  it("keeps a stream with a picture shown", () => {
    const tv = stream(1280);
    tv.fire("loadedmetadata");
    tv.fire("playing");
    expect(tv.picture()).toBe(1);
  });
});
