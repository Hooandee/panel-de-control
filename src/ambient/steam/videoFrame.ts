import { parseEmbedStream } from "../core/streams";
import { parseYouTube, youTubeThumbnail } from "../core/youtube";
import type { MediaLike, YouTubeTrackInfo } from "./youtubeEngine";

export interface VideoBounds {
  x: number;
  y: number;
  width: number;
  height: number;
  radius?: number;
}

interface PageState {
  s: "loading" | "playing" | "paused" | "ended" | "error";
  t: number;
  d: number;
  title: string;
  id: string;
  err: number;
  /** 0 once a direct stream turns out to carry sound only (a radio over HLS). */
  pic?: number;
}

type Command = "play" | "pause" | "seek" | "volume" | "next" | "previous";

export const LOAD_TIMEOUT_MS = 20000;

function randomKey(): string {
  const bytes = new Uint8Array(12);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}
/** Off screen but laid out: a zero-size or hidden frame never starts its media. */
export const PARKED: VideoBounds = { x: -10000, y: 0, width: 320, height: 180 };
export const STAGE_ID = "pdc-ambient-stage";
const RADIUS_PX = 18;
const STATE_EVENTS: Record<PageState["s"], string> = { loading: "waiting", playing: "playing", paused: "pause", ended: "ended", error: "error" };

/**
 * Panel's loopback player page in an iframe on Steam's main window, the window the floating card
 * lives in; it stays laid out off screen when only the sound is wanted. Commands and state travel
 * by postMessage.
 */
export class VideoFrameEngine extends EventTarget implements MediaLike {
  preload = "auto";
  error: { code: number } | null = null;
  duration = Number.NaN;
  hasPicture = true;
  private stage: HTMLDivElement | null = null;
  private frame: HTMLIFrameElement | null = null;
  private url = "";
  private time = 0;
  private level = 1;
  private ready = false;
  private pending = new Map<Command, unknown>();
  private loadTimer: ReturnType<typeof setTimeout> | null = null;
  private lastState: PageState["s"] | null = null;
  private videoId = "";
  private trackTitle = "";
  private bounds: VideoBounds | null = null;
  private visible = false;
  private generation = 0;
  private key = "";

  constructor(
    private readonly pageUrl: () => Promise<string | null>,
    private readonly hostDocument: () => Document | null,
  ) {
    super();
  }

  get src(): string {
    return this.url;
  }

  set src(url: string) {
    this.teardown();
    this.url = url;
    const generation = ++this.generation;
    void this.open(url, generation);
  }

  get volume(): number {
    return this.level;
  }

  set volume(value: number) {
    this.level = value;
    this.send("volume", Math.round(value * 100));
  }

  get currentTime(): number {
    return this.time;
  }

  set currentTime(value: number) {
    this.time = value;
    this.send("seek", Number(value) || 0);
  }

  play(): Promise<void> {
    this.pending.delete("pause");
    this.send("play");
    return Promise.resolve();
  }

  pause(): void {
    this.pending.delete("play");
    this.send("pause");
  }

  nextVideo(): void {
    this.send("next");
  }

  previousVideo(): void {
    this.send("previous");
  }

  setBounds(bounds: VideoBounds): void {
    this.bounds = bounds;
    this.place();
  }

  setVisible(visible: boolean): void {
    this.visible = visible;
    this.place();
  }

  load(): void {
    this.teardown();
  }

  removeAttribute(name: string): void {
    if (name === "src") this.teardown();
  }

  dispose(): void {
    this.teardown();
    this.stage?.remove();
    this.stage = null;
  }

  private ensureStage(): HTMLDivElement | null {
    const doc = this.hostDocument();
    if (!doc?.body) return null;
    if (this.stage && this.stage.ownerDocument === doc && this.stage.isConnected) return this.stage;
    doc.getElementById(STAGE_ID)?.remove();
    const stage = doc.createElement("div");
    stage.id = STAGE_ID;
    // Rounded corners must clip the embedded page too; a composited iframe ignores overflow + radius.
    stage.style.cssText = `position:fixed;z-index:2147482999;overflow:hidden;border-radius:${RADIUS_PX}px;clip-path:inset(0 round ${RADIUS_PX}px);background:#000;pointer-events:none`;
    doc.body.appendChild(stage);
    this.stage = stage;
    this.place();
    return stage;
  }

  private place(): void {
    const stage = this.stage;
    if (!stage) return;
    const b = this.visible && this.bounds ? this.bounds : PARKED;
    const radius = b.radius ?? RADIUS_PX;
    Object.assign(stage.style, { borderRadius: `${radius}px`, clipPath: `inset(0 round ${radius}px)`, left: `${Math.round(b.x)}px`, top: `${Math.round(b.y)}px`, width: `${Math.round(b.width)}px`, height: `${Math.round(b.height)}px` });
  }

  private async open(url: string, generation: number): Promise<void> {
    const base = await this.pageUrl().catch(() => null);
    if (generation !== this.generation) return;
    const stage = this.ensureStage();
    if (!base || !stage) {
      this.fail(5);
      return;
    }
    this.key = randomKey();
    const params = new URLSearchParams({ vol: String(Math.round(this.level * 100)), k: this.key });
    const ref = parseYouTube(url);
    const embed = ref ? null : parseEmbedStream(url);
    let page = base;
    if (ref?.videoId) params.set("yt", ref.videoId);
    if (ref?.listId) params.set("list", ref.listId);
    if (embed) {
      params.set("embed", embed.provider);
      params.set("ref", "channel" in embed && embed.channel ? embed.channel : "video" in embed && embed.video ? embed.video : "id" in embed ? embed.id : "");
      if (embed.provider === "twitch" && embed.video) params.set("vod", "1");
      // Twitch's embed requires `parent` to be a host name, so the page is opened by name.
      if (embed.provider === "twitch") page = base.replace("//127.0.0.1:", "//localhost:");
    }
    if (!ref && !embed) params.set("src", url);
    const frame = stage.ownerDocument.createElement("iframe");
    frame.allow = "autoplay; encrypted-media; fullscreen";
    frame.tabIndex = -1;
    // The card draws its own controls; a provider's overlay (YouTube's title, "More videos") only
    // appears on pointer contact, so the picture never takes it.
    frame.style.cssText = "position:absolute;inset:0;width:100%;height:100%;border:0;pointer-events:none";
    frame.src = `${page}?${params.toString()}`;
    stage.ownerDocument.defaultView?.addEventListener("message", this.onMessage);
    stage.appendChild(frame);
    this.frame = frame;
    this.dispatchEvent(new Event("waiting"));
    this.loadTimer = setTimeout(() => {
      if (!this.ready) this.fail(5);
    }, LOAD_TIMEOUT_MS);
  }

  private send(command: Command, arg?: unknown): void {
    if (!this.frame) return;
    if (!this.ready) {
      this.pending.set(command, arg);
      return;
    }
    this.frame.contentWindow?.postMessage({ pdcCmd: command, arg, k: this.key }, "*");
  }

  private readonly onMessage = (event: MessageEvent): void => {
    if (!this.frame || event.source !== this.frame.contentWindow) return;
    const state = (event.data as { pdc?: PageState } | null)?.pdc;
    if (!state || typeof state !== "object") return;
    if (!this.ready) {
      this.ready = true;
      const queued = [...this.pending.entries()];
      this.pending.clear();
      for (const [command, arg] of queued) this.frame.contentWindow?.postMessage({ pdcCmd: command, arg, k: this.key }, "*");
    }
    this.read(state);
  };

  private read(state: PageState): void {
    const picture = state.pic !== 0;
    if (picture !== this.hasPicture) {
      this.hasPicture = picture;
      this.dispatchEvent(new Event("picturechange"));
    }
    if (state.s === "error") {
      if (this.lastState !== "error") this.fail(state.err || 0);
      this.lastState = "error";
      return;
    }
    if (state.d > 0 && state.d !== this.duration) {
      this.duration = state.d;
      this.dispatchEvent(new Event("loadedmetadata"));
    }
    this.time = state.t;
    this.dispatchEvent(new Event("timeupdate"));
    if (state.s !== this.lastState) {
      this.lastState = state.s;
      this.dispatchEvent(new Event(STATE_EVENTS[state.s]));
    }
    if (state.id && (state.id !== this.videoId || (state.title && state.title !== this.trackTitle))) {
      this.videoId = state.id;
      this.trackTitle = state.title;
      const detail: YouTubeTrackInfo = { title: state.title, art: youTubeThumbnail(state.id) };
      this.dispatchEvent(new CustomEvent("trackinfo", { detail }));
    }
  }

  private fail(code: number): void {
    this.error = { code };
    this.dispatchEvent(new Event("error"));
  }

  private teardown(): void {
    this.generation += 1;
    if (this.loadTimer !== null) clearTimeout(this.loadTimer);
    this.loadTimer = null;
    this.frame?.ownerDocument.defaultView?.removeEventListener("message", this.onMessage);
    this.frame?.remove();
    this.frame = null;
    this.url = "";
    this.error = null;
    this.time = 0;
    this.duration = Number.NaN;
    this.ready = false;
    this.pending.clear();
    this.lastState = null;
    this.videoId = "";
    this.trackTitle = "";
    this.hasPicture = true;
  }
}
