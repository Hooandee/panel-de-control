// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LOAD_TIMEOUT_MS, PARKED, STAGE_ID, VideoFrameEngine } from "./videoFrame";

const PAGE = "http://127.0.0.1:4000/v/token/player.html";

async function opened(engine: VideoFrameEngine, url: string): Promise<HTMLIFrameElement> {
  engine.src = url;
  let frame: HTMLIFrameElement | null = null;
  await vi.waitFor(() => {
    frame = document.querySelector(`#${STAGE_ID} iframe`);
    expect(frame).not.toBeNull();
  });
  return frame!;
}

function stage(): HTMLElement {
  return document.getElementById(STAGE_ID)!;
}

function fromPage(frame: HTMLIFrameElement, state: object): void {
  window.dispatchEvent(new MessageEvent("message", { data: { pdc: state }, source: frame.contentWindow as Window }));
}

describe("VideoFrameEngine", () => {
  beforeEach(() => {
    const create = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation(((tag: string) => {
      const element = create(tag);
      if (tag === "iframe") {
        let src = "";
        Object.defineProperty(element, "src", { get: () => src, set: (value: string) => { src = value; } });
      }
      return element;
    }) as typeof document.createElement);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
    document.body.innerHTML = "";
  });

  it("opens the page with the stream, parked until shown, rounded when placed", async () => {
    const engine = new VideoFrameEngine(async () => PAGE, () => document);
    engine.setBounds({ x: 10, y: 20, width: 300, height: 170 });
    const frame = await opened(engine, "https://www.youtube.com/watch?v=dsuJZx24V_A&list=RDdsuJZx24V_A");
    const url = new URL(frame.src);
    expect(url.origin + url.pathname).toBe(PAGE);
    expect(url.searchParams.get("yt")).toBe("dsuJZx24V_A");
    expect(stage().style.left).toBe(`${PARKED.x}px`);
    engine.setVisible(true);
    expect([stage().style.left, stage().style.top, stage().style.width]).toEqual(["10px", "20px", "300px"]);
    expect(stage().style.borderRadius).not.toBe("");
    engine.dispose();
    expect(document.getElementById(STAGE_ID)).toBeNull();
  });

  it("opens Twitch by host name and other streams as plain sources", async () => {
    const engine = new VideoFrameEngine(async () => PAGE, () => document);
    const twitch = await opened(engine, "https://www.twitch.tv/ibai");
    expect(twitch.src.startsWith("http://localhost:4000/")).toBe(true);
    const hls = await opened(engine, "https://tv.test/la1.m3u8");
    expect(hls).not.toBe(twitch);
    expect(new URL(hls.src).searchParams.get("src")).toBe("https://tv.test/la1.m3u8");
  });

  it("turns page messages into media events and holds commands until the page answers", async () => {
    const engine = new VideoFrameEngine(async () => PAGE, () => document);
    const events: string[] = [];
    for (const type of ["playing", "timeupdate", "loadedmetadata", "trackinfo"]) engine.addEventListener(type, () => events.push(type));
    const frame = await opened(engine, "https://youtu.be/dsuJZx24V_A");
    const sent = vi.spyOn(frame.contentWindow as Window, "postMessage");
    engine.pause();
    expect(sent).not.toHaveBeenCalled();
    fromPage(frame, { s: "playing", t: 12, d: 200, title: "Life Will Change", id: "dsuJZx24V_A", err: 0 });
    const key = new URL(frame.src).searchParams.get("k");
    expect(key).toMatch(/^[0-9a-f]{24}$/);
    expect(sent).toHaveBeenCalledWith({ pdcCmd: "pause", arg: undefined, k: key }, "*");
    expect(events).toEqual(["loadedmetadata", "timeupdate", "playing", "trackinfo"]);
    expect(engine.currentTime).toBe(12);
    engine.dispose();
  });

  it("tells when a stream carries sound only and forgets it on the next source", async () => {
    const engine = new VideoFrameEngine(async () => PAGE, () => document);
    const changes: boolean[] = [];
    engine.addEventListener("picturechange", () => changes.push(engine.hasPicture));
    const frame = await opened(engine, "https://radio.test/live.m3u8");
    fromPage(frame, { s: "playing", t: 3, d: 0, title: "", id: "", err: 0, pic: 0 });
    fromPage(frame, { s: "playing", t: 4, d: 0, title: "", id: "", err: 0, pic: 0 });
    expect(changes).toEqual([false]);
    engine.removeAttribute("src");
    expect(engine.hasPicture).toBe(true);
    engine.dispose();
  });

  it("reports an error when the page never answers", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const engine = new VideoFrameEngine(async () => PAGE, () => document);
    const errors: number[] = [];
    engine.addEventListener("error", () => errors.push(engine.error?.code ?? -1));
    await opened(engine, "https://tv.test/la1.m3u8");
    vi.advanceTimersByTime(LOAD_TIMEOUT_MS + 10);
    expect(errors).toEqual([5]);
    engine.dispose();
  });

  it("propagates confirmed Vimeo progress and generic failure after the bridge is ready", async () => {
    const engine = new VideoFrameEngine(async () => PAGE, () => document);
    const events: string[] = [];
    for (const type of ["waiting", "playing", "pause", "ended", "error"]) engine.addEventListener(type, () => events.push(type));
    const frame = await opened(engine, "https://vimeo.com/76979871");
    fromPage(frame, { s: "loading", t: 0, d: 0, title: "76979871", id: "", err: 0 });
    expect(events).not.toContain("playing");
    fromPage(frame, { s: "playing", t: 12, d: 100, title: "76979871", id: "", err: 0 });
    expect(engine.currentTime).toBe(12);
    expect(engine.duration).toBe(100);
    fromPage(frame, { s: "paused", t: 12, d: 100, title: "76979871", id: "", err: 0 });
    fromPage(frame, { s: "ended", t: 100, d: 100, title: "76979871", id: "", err: 0 });
    fromPage(frame, { s: "error", t: 100, d: 100, title: "76979871", id: "", err: 0 });
    expect(events.slice(-4)).toEqual(["playing", "pause", "ended", "error"]);
    expect(engine.error?.code).toBe(0);
    engine.dispose();
  });
  it("resizes the same playing frame to fullscreen and back without changing time or volume", async () => {
    const engine = new VideoFrameEngine(async () => PAGE, () => document);
    const small = { x: 500, y: 20, width: 320, height: 180 };
    engine.setBounds(small);
    engine.setVisible(true);
    const frame = await opened(engine, "https://tv.test/la1.m3u8");
    const src = frame.src;
    engine.volume = 0.37;
    fromPage(frame, { s: "playing", t: 42, d: 200, title: "", id: "", err: 0 });
    const sent = vi.spyOn(frame.contentWindow as Window, "postMessage");
    engine.setBounds({ x: 0, y: 40, width: 1280, height: 720, radius: 0 });
    expect(stage().style.borderRadius).toBe("0px");
    expect(document.querySelector(`#${STAGE_ID} iframe`)).toBe(frame);
    expect(frame.src).toBe(src);
    expect(engine.currentTime).toBe(42);
    expect(engine.volume).toBe(0.37);
    engine.setBounds(small);
    expect(stage().style.left).toBe("500px");
    expect(stage().style.borderRadius).toBe("18px");
    expect(sent).not.toHaveBeenCalled();
    engine.dispose();
  });

});
