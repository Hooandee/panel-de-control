import { BLEND_GAME_ART_OPACITY, type NativeArt } from "../core/gameArtBlend";
import type { MotionState } from "../core/powerPolicy";
import { steamClass } from "./steamClasses";

export interface LayerMedia {
  url: string;
  /** "page" is Panel's loopback player page, for streams a plain <video> cannot play (HLS trailers). */
  kind: "image" | "video" | "page";
}

export interface LayerOptions {
  transition: "fade" | "kenburns";
  nativeArt: NativeArt;
  motion: MotionState;
  visible: boolean;
}

const ROOT_ID = "pdc-ambient-layer";
const STYLE_ID = "pdc-ambient-layer-style";
const FADE_MS = 900;
const PAGE_START_MS = 8000;
/** Quick retries for a blip, then slower ones: after a Steam restart Panel's media server can come up late. */
const RETRY_DELAYS_MS = [1000, 3000, 10_000, 30_000, 60_000];
const TRAILER_RETRY_DELAYS_MS = [1000, 3000];
const STALL_CHECK_MS = 5000;
/** Checks in a row without the playing video moving before it is loaded again. */
const STALL_CHECKS = 2;
const STALL_RELOADS = 3;
const HOST_KEY = "BasicHome";
const ART_ATTR = "data-pdc-ambient-art";
/**
 * Steam paints the focused game's hero inside Home's content, above this layer, each image in its own
 * wrapper. Older clients only mark it by the blurred hero file; current ones load library_hero.jpg.
 */
const LEGACY_NATIVE_ART = `div:has(> img[src*="library_hero_blur"])`;
const NATIVE_ART_KEY = "RecentGamesBackground";
/**
 * The box holding those wrappers. Steam leaves it transparent, but CSS Loader themes tint it (Obsidian's
 * "Recent Games Background" paints it a solid colour and multiplies the hero over it): hiding only the
 * hero left that colour covering Panel's background and trailers.
 */
const NATIVE_ART_BOX_KEY = "RecentGamesBackgroundImages";

function layerCss(nativeArtClass: string | null, nativeArtBoxClass: string | null): string {
  const nativeArt = nativeArtClass ? [LEGACY_NATIVE_ART, `.${nativeArtClass}`] : [LEGACY_NATIVE_ART];
  const forRoot = (state: string) => nativeArt.map((selector) => `:root[${ART_ATTR}=${state}] ${selector}`).join(",");
  const box = nativeArtBoxClass
    ? `:root[${ART_ATTR}=hide] .${nativeArtBoxClass},:root[${ART_ATTR}=blend] .${nativeArtBoxClass}{background:none!important}`
    : "";
  return `
#${ROOT_ID}{position:absolute;inset:0;z-index:-1;pointer-events:none;overflow:hidden;contain:strict}
#${ROOT_ID}>[data-slot]{position:absolute;inset:0;opacity:0;transition:opacity ${FADE_MS}ms ease}
#${ROOT_ID}>[data-slot][data-active]{opacity:1}
#${ROOT_ID} [data-media]{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
#${ROOT_ID}[data-transition=kenburns] [data-active] [data-media]{animation:pdc-ambient-kb 24s ease-in-out infinite alternate}
#${ROOT_ID}[data-motion=pause] [data-media],#${ROOT_ID}[data-motion=freeze] [data-media]{animation-play-state:paused}
${nativeArt.join(",")}{transition:opacity 400ms ease}
${forRoot("hide")}{opacity:0!important}
${forRoot("blend")}{opacity:${BLEND_GAME_ART_OPACITY}!important}
${box}
@keyframes pdc-ambient-kb{from{transform:scale(1)}to{transform:scale(1.07) translate(-1.2%,-1%)}}
@media (prefers-reduced-motion:reduce){#${ROOT_ID} [data-media]{animation:none!important}#${ROOT_ID}>[data-slot]{transition:none}}
`;
}

/**
 * Panel's media server answers the Steam UI with CORS headers; asking for them keeps its pictures and
 * videos readable by a theme's canvas or WebGL (a reflection of the background) instead of tainting it.
 * Other origins are left alone: one without those headers would refuse to load at all.
 */
function readableFrom(element: HTMLImageElement | HTMLVideoElement, url: string): void {
  try {
    if (new URL(url).hostname === "127.0.0.1") element.crossOrigin = "anonymous";
  } catch {
    // Not an absolute URL: same origin, already readable.
  }
}

/**
 * Reads an image once at screen size so large photos do not sit in memory at full resolution.
 * A bitmaprenderer canvas paints blank in Steam's CEF, so the result is a downscaled blob in an <img>.
 */
async function screenSizedImage(doc: Document, url: string): Promise<HTMLImageElement> {
  const view = doc.defaultView;
  const width = Math.round((view?.innerWidth ?? 1280) * (view?.devicePixelRatio ?? 1));
  const img = doc.createElement("img");
  img.decoding = "async";
  try {
    const blob = await (await fetch(url)).blob();
    const bitmap = await createImageBitmap(blob);
    if (bitmap.width > width * 1.25) {
      const height = Math.round(bitmap.height * (width / bitmap.width));
      const canvas = new OffscreenCanvas(width, height);
      const context = canvas.getContext("2d");
      if (!context) throw new Error("no 2d context");
      context.imageSmoothingQuality = "high";
      context.drawImage(bitmap, 0, 0, width, height);
      bitmap.close();
      img.src = URL.createObjectURL(await canvas.convertToBlob({ type: "image/jpeg", quality: 0.9 }));
      img.dataset.objectUrl = "";
    } else {
      bitmap.close();
      readableFrom(img, url);
      img.src = url;
    }
  } catch {
    readableFrom(img, url);
    img.src = url;
  }
  await img.decode().catch(() => undefined);
  return img;
}

type LoadResult = "ready" | "error" | "timeout" | "cancelled" | "no_picture";

/** What the reports need to tell a missing codec, a dead stream and a stalled decoder apart. */
function videoState(video: HTMLVideoElement): string {
  return `ready=${video.readyState} net=${video.networkState} err=${video.error?.code ?? 0} size=${video.videoWidth}x${video.videoHeight} t=${video.currentTime.toFixed(1)} paused=${video.paused}`;
}
/** Every attempt owns its listeners and deadline, including cancellation on replacement. */
function waitForMedia(element: HTMLVideoElement | HTMLIFrameElement, signal: AbortSignal): Promise<LoadResult> {
  return new Promise((resolve) => {
    const view = element.ownerDocument.defaultView;
    const done = (result: LoadResult) => {
      clearTimeout(timer);
      element.removeEventListener("loadeddata", ready);
      element.removeEventListener("error", error);
      view?.removeEventListener("message", message);
      signal.removeEventListener("abort", cancel);
      resolve(result);
    };
    const ready = () => done("ready");
    const error = () => done("error");
    const cancel = () => done("cancelled");
    const message = (event: MessageEvent) => {
      if (element.tagName !== "IFRAME" || event.source !== (element as HTMLIFrameElement).contentWindow) return;
      const state = (event.data as { pdc?: { s?: string } } | null)?.pdc?.s;
      if (state === "playing") ready();
      else if (state === "error") error();
    };
    const timer = setTimeout(() => done("timeout"), PAGE_START_MS);
    if (element.tagName === "VIDEO") element.addEventListener("loadeddata", ready);
    element.addEventListener("error", error);
    view?.addEventListener("message", message);
    signal.addEventListener("abort", cancel, { once: true });
    if (signal.aborted) cancel();
  });
}

function release(container: Element): void {
  container.querySelectorAll("video").forEach((video) => {
    video.pause();
    video.removeAttribute("src");
    video.load();
  });
  container.querySelectorAll<HTMLImageElement>("img[data-object-url]").forEach((img) => URL.revokeObjectURL(img.src));
}

export class BackgroundLayer {
  private root: HTMLDivElement | null = null;
  private host: HTMLElement | null = null;
  private hostIsolation = "";
  private current: LayerMedia | null = null;
  private options: LayerOptions = { transition: "fade", nativeArt: "show", motion: "play", visible: true };
  private generation = 0;
  private load: AbortController | null = null;
  private lastFailure = "";
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private fadeTimer: ReturnType<typeof setTimeout> | null = null;
  private stallTimer: ReturnType<typeof setInterval> | null = null;
  private stall = { at: -1, checks: 0, reloads: 0, url: "" };

  constructor(
    private readonly getDocument: () => Document | null,
    private readonly onVideoSize: (url: string, width: number, height: number) => void = () => undefined,
    private readonly onLoadFailure: (detail: string) => void = () => undefined,
  ) {}

  get mounted(): boolean {
    return !!this.root?.isConnected;
  }

  private ensureMounted(): boolean {
    const doc = this.getDocument();
    const hostClass = steamClass(HOST_KEY);
    if (!doc || !hostClass) return false;
    const host = doc.querySelector<HTMLElement>(`.${hostClass}`);
    if (!host) return false;
    if (this.root?.isConnected && this.root.parentElement === host) return true;
    this.unmount();
    if (!doc.getElementById(STYLE_ID)) {
      const style = doc.createElement("style");
      style.id = STYLE_ID;
      style.textContent = layerCss(steamClass(NATIVE_ART_KEY), steamClass(NATIVE_ART_BOX_KEY));
      doc.head.appendChild(style);
    }
    const root = doc.createElement("div");
    root.id = ROOT_ID;
    root.setAttribute("aria-hidden", "true");
    for (const name of ["a", "b"]) {
      const slot = doc.createElement("div");
      slot.dataset.slot = name;
      root.appendChild(slot);
    }
    this.hostIsolation = host.style.isolation;
    host.style.isolation = "isolate";
    host.prepend(root);
    this.host = host;
    this.root = root;
    this.current = null;
    return true;
  }

  apply(media: LayerMedia | null, options: LayerOptions): boolean {
    this.options = options;
    if (media === null) {
      this.dispose();
      return true;
    }
    if (!this.ensureMounted() || !this.root) return false;
    const root = this.root;
    root.dataset.transition = options.transition;
    root.dataset.motion = options.motion;
    this.syncNativeArt();
    root.style.display = options.visible ? "" : "none";
    if (!this.current || this.current.url !== media.url || this.current.kind !== media.kind) void this.swap(media);
    this.syncVideos();
    return true;
  }

  private syncNativeArt(): void {
    if (!this.root) return;
    const page = this.root.ownerDocument.documentElement;
    if (!this.root.querySelector("[data-active]") || this.options.nativeArt === "show") page.removeAttribute(ART_ATTR);
    else page.setAttribute(ART_ATTR, this.options.nativeArt);
  }

  private cancelPending(): void {
    this.load?.abort();
    this.load = null;
    if (this.retryTimer !== null) clearTimeout(this.retryTimer);
    if (this.fadeTimer !== null) clearTimeout(this.fadeTimer);
    this.retryTimer = this.fadeTimer = null;
  }

  private async swap(media: LayerMedia, attempt = 0): Promise<void> {
    const root = this.root;
    const doc = this.getDocument();
    if (!root || !doc) return;
    this.cancelPending();
    const generation = ++this.generation;
    const load = new AbortController();
    this.load = load;
    this.current = media;
    const slots = Array.from(root.querySelectorAll<HTMLElement>("[data-slot]"));
    const incoming = slots.find((slot) => !slot.hasAttribute("data-active")) ?? slots[0];
    const outgoing = slots.find((slot) => slot !== incoming);
    release(incoming);
    incoming.replaceChildren();
    let element: HTMLElement;
    let result: LoadResult = "ready";
    if (media.kind === "video") {
      const video = doc.createElement("video");
      video.muted = true;
      video.loop = true;
      video.playsInline = true;
      video.preload = "auto";
      video.dataset.media = "";
      readableFrom(video, media.url);
      incoming.replaceChildren(video);
      const ready = waitForMedia(video, load.signal);
      video.src = media.url;
      result = await ready;
      // Sound but no picture (a codec the GPU decoder lost, an audio-only file) paints a flat grey box.
      if (result === "ready" && video.videoHeight === 0) result = "no_picture";
      if (result === "ready" && generation === this.generation) this.onVideoSize(media.url, video.videoWidth, video.videoHeight);
      if (result !== "ready" && result !== "cancelled") this.lastFailure = videoState(video);
      element = video;
    } else if (media.kind === "page") {
      const frame = doc.createElement("iframe");
      frame.allow = "autoplay";
      frame.tabIndex = -1;
      frame.style.border = "0";
      frame.style.pointerEvents = "none";
      incoming.replaceChildren(frame);
      const ready = waitForMedia(frame, load.signal);
      frame.src = media.url;
      result = await ready;
      element = frame;
    } else {
      element = await screenSizedImage(doc, media.url);
    }
    if (generation !== this.generation || !this.root) return;
    this.load = null;
    if (result !== "ready") {
      release(incoming);
      incoming.replaceChildren();
      this.syncNativeArt();
      if (result !== "cancelled") {
        const delays = media.kind === "page" ? TRAILER_RETRY_DELAYS_MS : RETRY_DELAYS_MS;
        const retrying = attempt < delays.length;
        const state = media.kind === "video" && this.lastFailure ? `; ${this.lastFailure}` : "";
        this.lastFailure = "";
        this.onLoadFailure(`background ${media.kind} ${result}; attempt=${attempt + 1}; retrying=${retrying}${state}`);
        if (retrying) this.retryTimer = setTimeout(() => {
          this.retryTimer = null;
          if (generation === this.generation) void this.swap(media, attempt + 1);
        }, delays[attempt]);
      }
      return;
    }
    element.dataset.media = "";
    if (element.parentElement !== incoming) incoming.replaceChildren(element);
    incoming.setAttribute("data-active", "");
    outgoing?.removeAttribute("data-active");
    this.syncNativeArt();
    this.syncVideos();
    this.fadeTimer = setTimeout(() => {
      this.fadeTimer = null;
      if (generation !== this.generation || !outgoing) return;
      release(outgoing);
      outgoing.replaceChildren();
    }, FADE_MS + 100);
  }

  /** The picture or video on screen now, readable by canvas and WebGL; null for none or a player page. */
  activeMedia(): HTMLImageElement | HTMLVideoElement | null {
    const media = this.root?.querySelector("[data-slot][data-active] [data-media]");
    if (!media || this.root?.style.display === "none") return null;
    const view = media.ownerDocument.defaultView;
    if (view && (media instanceof view.HTMLImageElement || media instanceof view.HTMLVideoElement)) return media;
    return null;
  }

  private syncVideos(): void {
    const play = this.options.motion === "play" && this.options.visible;
    this.root?.querySelectorAll("video").forEach((video) => {
      if (play && video.closest("[data-active]")) void video.play().catch(() => undefined);
      else video.pause();
    });
    this.watchStall(play && !!this.root?.querySelector("[data-slot][data-active] video"));
  }

  /**
   * A background video that should play but no longer moves (a decoder lost after leaving desktop
   * mode, a stream that dried up) is loaded again, a few times per video, instead of staying black.
   */
  private watchStall(active: boolean): void {
    if (!active) {
      if (this.stallTimer !== null) clearInterval(this.stallTimer);
      this.stallTimer = null;
      this.stall.at = -1;
      this.stall.checks = 0;
      return;
    }
    if (this.stallTimer !== null) return;
    this.stallTimer = setInterval(() => this.checkStall(), STALL_CHECK_MS);
  }

  private checkStall(): void {
    const video = this.root?.querySelector<HTMLVideoElement>("[data-slot][data-active] video");
    const media = this.current;
    if (!video || !media || media.kind !== "video" || this.load) return this.watchStall(false);
    if (this.stall.url !== media.url) this.stall = { at: -1, checks: 0, reloads: 0, url: media.url };
    const moved = video.currentTime !== this.stall.at;
    this.stall.at = video.currentTime;
    if (moved && !video.error) {
      this.stall.checks = 0;
      return;
    }
    if (video.paused && !video.error) void video.play().catch(() => undefined);
    if (++this.stall.checks < STALL_CHECKS && !video.error) return;
    this.stall.checks = 0;
    const reloading = this.stall.reloads < STALL_RELOADS;
    this.onLoadFailure(`background video stalled; reload=${this.stall.reloads + 1}; reloading=${reloading}; ${videoState(video)}`);
    if (!reloading) return this.watchStall(false);
    this.stall.reloads += 1;
    this.current = null;
    void this.swap(media);
  }

  private unmount(): void {
    this.cancelPending();
    this.watchStall(false);
    this.generation += 1;
    if (this.root) release(this.root);
    this.root?.remove();
    if (this.host) this.host.style.isolation = this.hostIsolation;
    this.root = null;
    this.host = null;
    this.current = null;
  }

  /** Chromium can drop rasterized tiles on resume and only redraws what changes; nudge the layer. */
  repaint(): void {
    const root = this.root;
    if (!root) return;
    const view = this.getDocument()?.defaultView;
    root.style.outline = "1px solid rgba(0,0,0,0.004)";
    const clear = () => { root.style.outline = ""; };
    if (view?.requestAnimationFrame) view.requestAnimationFrame(() => view.requestAnimationFrame(clear));
    else setTimeout(clear, 50);
  }

  dispose(): void {
    this.unmount();
    this.getDocument()?.documentElement.removeAttribute(ART_ATTR);
    this.getDocument()?.getElementById(STYLE_ID)?.remove();
  }
}
