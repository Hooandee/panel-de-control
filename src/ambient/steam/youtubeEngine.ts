import { parseYouTube, youTubeEmbedUrl, youTubeThumbnail } from "../core/youtube";

/** The slice of HTMLMediaElement the player drives, so YouTube can stand in for `<audio>`. */
export interface MediaLike extends EventTarget {
  src: string;
  volume: number;
  currentTime: number;
  readonly duration: number;
  readonly error: { code: number } | null;
  preload: string;
  play(): Promise<void>;
  pause(): void;
  load(): void;
  removeAttribute(name: string): void;
}

export interface YouTubeTrackInfo {
  title: string;
  art: string;
}

const HANDSHAKE_MS = 250;
const HANDSHAKE_TRIES = 40;
const STATE_EVENTS: Record<number, string> = { 0: "ended", 1: "playing", 2: "pause", 3: "waiting" };

/**
 * Official YouTube embed, kept off-screen, driven through its postMessage API. Audio from the
 * shared context keeps playing while a game runs, like the radio.
 */
export class YouTubeEngine extends EventTarget implements MediaLike {
  preload = "auto";
  error: { code: number } | null = null;
  duration = Number.NaN;
  private frame: HTMLIFrameElement | null = null;
  private url = "";
  private time = 0;
  private level = 1;
  private ready = false;
  private handshake: ReturnType<typeof setInterval> | null = null;
  private pending: [string, unknown[]][] = [];
  private videoId: string | null = null;
  private title = "";

  constructor(private readonly host: Window = window) {
    super();
    host.addEventListener("message", this.onMessage);
  }

  get src(): string {
    return this.url;
  }

  set src(url: string) {
    this.teardown();
    this.url = url;
    const ref = parseYouTube(url);
    if (!ref) {
      this.fail(2);
      return;
    }
    const frame = this.host.document.createElement("iframe");
    frame.allow = "autoplay; encrypted-media";
    frame.setAttribute("aria-hidden", "true");
    frame.tabIndex = -1;
    frame.style.cssText = "position:fixed;left:-10000px;top:0;width:320px;height:180px;border:0;pointer-events:none";
    frame.src = youTubeEmbedUrl(ref, this.host.location.origin);
    frame.addEventListener("load", () => this.startHandshake(), { once: true });
    this.host.document.body.appendChild(frame);
    this.frame = frame;
    this.dispatchEvent(new Event("waiting"));
  }

  get volume(): number {
    return this.level;
  }

  set volume(value: number) {
    this.level = value;
    this.command("setVolume", [Math.round(value * 100)]);
  }

  get currentTime(): number {
    return this.time;
  }

  set currentTime(value: number) {
    this.time = value;
    this.command("seekTo", [value, true]);
  }

  play(): Promise<void> {
    this.command("playVideo", []);
    return Promise.resolve();
  }

  pause(): void {
    this.command("pauseVideo", []);
  }

  nextVideo(): void {
    this.command("nextVideo", []);
  }

  previousVideo(): void {
    this.command("previousVideo", []);
  }

  load(): void {
    this.teardown();
  }

  removeAttribute(name: string): void {
    if (name === "src") this.teardown();
  }

  dispose(): void {
    this.teardown();
    this.host.removeEventListener("message", this.onMessage);
  }

  private teardown(): void {
    if (this.handshake !== null) clearInterval(this.handshake);
    this.handshake = null;
    this.frame?.remove();
    this.frame = null;
    this.url = "";
    this.ready = false;
    this.pending = [];
    this.error = null;
    this.time = 0;
    this.duration = Number.NaN;
    this.videoId = null;
    this.title = "";
  }

  private startHandshake(): void {
    let tries = 0;
    const listen = () => {
      if (this.ready || ++tries > HANDSHAKE_TRIES) {
        if (this.handshake !== null) clearInterval(this.handshake);
        this.handshake = null;
        if (!this.ready && this.frame) this.fail(5);
        return;
      }
      this.post({ event: "listening", id: 1, channel: "widget" });
    };
    listen();
    this.handshake = setInterval(listen, HANDSHAKE_MS);
  }

  private command(func: string, args: unknown[]): void {
    if (!this.frame) return;
    if (!this.ready) {
      this.pending = [...this.pending.filter(([f]) => f !== func), [func, args]];
      return;
    }
    this.post({ event: "command", func, args, id: 1, channel: "widget" });
  }

  private post(message: object): void {
    this.frame?.contentWindow?.postMessage(JSON.stringify(message), "https://www.youtube.com");
  }

  private fail(code: number): void {
    this.error = { code };
    this.dispatchEvent(new Event("error"));
  }

  private readonly onMessage = (event: MessageEvent): void => {
    if (!this.frame || event.source !== this.frame.contentWindow || typeof event.data !== "string") return;
    let data: { event?: string; info?: unknown };
    try {
      data = JSON.parse(event.data);
    } catch {
      return;
    }
    if (!this.ready && (data.event === "onReady" || data.event === "initialDelivery" || data.event === "infoDelivery")) {
      this.ready = true;
      const queued = this.pending;
      this.pending = [];
      this.post({ event: "command", func: "setVolume", args: [Math.round(this.level * 100)], id: 1, channel: "widget" });
      for (const [func, args] of queued) this.post({ event: "command", func, args, id: 1, channel: "widget" });
    }
    if (data.event === "onError") {
      this.fail(typeof data.info === "number" ? data.info : 0);
      return;
    }
    if (data.event === "onStateChange" && typeof data.info === "number") {
      this.state(data.info);
      return;
    }
    if (data.info && typeof data.info === "object") this.info(data.info as Record<string, unknown>);
  };

  private state(value: number): void {
    const type = STATE_EVENTS[value];
    if (type) this.dispatchEvent(new Event(type));
  }

  private info(info: Record<string, unknown>): void {
    if (typeof info.playerState === "number") this.state(info.playerState);
    if (typeof info.duration === "number" && info.duration > 0 && info.duration !== this.duration) {
      this.duration = info.duration;
      this.dispatchEvent(new Event("loadedmetadata"));
    }
    if (typeof info.currentTime === "number") {
      this.time = info.currentTime;
      this.dispatchEvent(new Event("timeupdate"));
    }
    const video = info.videoData as { video_id?: unknown; title?: unknown } | undefined;
    if (!video || typeof video.video_id !== "string" || !video.video_id) return;
    const title = typeof video.title === "string" ? video.title : "";
    if (video.video_id !== this.videoId || (title && title !== this.title)) {
      this.videoId = video.video_id;
      this.title = title;
      const detail: YouTubeTrackInfo = { title, art: youTubeThumbnail(video.video_id) };
      this.dispatchEvent(new CustomEvent("trackinfo", { detail }));
    }
  }
}
