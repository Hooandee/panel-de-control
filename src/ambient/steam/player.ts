import { playbackProblem } from "../core/playbackErrors";
import { nextRetryDelay } from "../core/playbackPolicy";
import * as playQueue from "../core/playQueue";
import type { QueueState, RepeatMode } from "../core/playQueue";
import { parseEmbedStream } from "../core/streams";
import { canShowVideo, isHls, parseYouTube } from "../core/youtube";
import type { VideoBounds } from "./videoFrame";
import { YouTubeEngine, type MediaLike, type YouTubeTrackInfo } from "./youtubeEngine";

export type PlayerStatus = "idle" | "loading" | "playing" | "paused" | "retrying" | "error";

export interface Track {
  id: string;
  title: string;
  subtitle: string;
  art: string;
  url: string;
  live: boolean;
  countryCode?: string;
  kind?: "audio" | "video";
}

export interface PlayerSnapshot {
  status: PlayerStatus;
  track: Track | null;
  volume: number;
  error: string | null;
  position: number;
  duration: number | null;
  /** The track is showing in Steam's video window instead of playing hidden. */
  video: boolean;
  /** False once the stream proved to carry sound only, so there is no picture to show. */
  picture: boolean;
  queue: QueueItem[];
  queueIndex: number;
  repeat: RepeatMode;
  shuffle: boolean;
}

export interface QueueItem {
  key: string;
  track: Track;
}

export interface PlayerCheckpoint {
  queue: QueueState<Track>;
  snapshot: PlayerSnapshot;
  playing: boolean;
  videoMode: boolean;
  scale: number;
}

type Listener = (snapshot: PlayerSnapshot) => void;
type AudioFactory = () => MediaLike;
type YouTubeFactory = () => MediaLike & Pick<YouTubeEngine, "nextVideo" | "previousVideo" | "dispose">;
type VideoFactory = () => ReturnType<YouTubeFactory> & { setBounds(bounds: VideoBounds): void; setVisible(visible: boolean): void };

export function isYouTubeTrack(track: Track): boolean {
  return parseYouTube(track.url) !== null;
}

export function hasYouTubeList(track: Track): boolean {
  return !!parseYouTube(track.url)?.listId;
}

/** Streams picked from Radio follow the radio's in-game rule, YouTube included. */
export function trackSource(track: Track): "music" | "radio" {
  return track.live || isYouTubeTrack(track) || parseEmbedStream(track.url) ? "radio" : "music";
}

/** One player for music, radio and YouTube. What the UI shows comes from the element's own events. */
export class AmbientPlayer {
  private audio: MediaLike | null = null;
  private youtube: ReturnType<YouTubeFactory> | null = null;
  private video: ReturnType<VideoFactory> | null = null;
  private videoMode = false;
  private active: MediaLike | null = null;
  private queue: QueueState<Track> = playQueue.emptyQueue();
  private volume = 0.5;
  private scale = 1;
  private attempt = 0;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private listeners = new Set<Listener>();
  private snapshot: PlayerSnapshot = { status: "idle", track: null, volume: 0.5, error: null, position: 0, duration: null, video: false, picture: true, queue: [], queueIndex: 0, repeat: "all", shuffle: false };
  private lastTimeEmit = 0;
  private wantPlaying = false;
  private disposed = false;
  private loadGeneration = 0;
  private pendingPosition: number | null = null;

  constructor(
    private readonly createAudio: AudioFactory = () => new Audio(),
    private readonly onError: (detail: string) => void = () => undefined,
    private readonly createYouTube: YouTubeFactory = () => new YouTubeEngine(),
    private readonly createVideo: VideoFactory | null = null,
  ) {}

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    listener(this.snapshot);
    return () => this.listeners.delete(listener);
  }

  getSnapshot(): PlayerSnapshot {
    return this.snapshot;
  }

  private emit(patch: Partial<PlayerSnapshot>): void {
    this.snapshot = { ...this.snapshot, ...patch };
    for (const listener of this.listeners) listener(this.snapshot);
  }

  private element(track: Track): MediaLike {
    const kind = this.engineFor(track);
    const element = kind === "video"
      ? (this.video ??= this.wire(this.createVideo!()))
      : kind === "youtube" ? (this.youtube ??= this.wire(this.createYouTube())) : (this.audio ??= this.wire(this.createAudio()));
    const previous = this.active;
    this.active = element;
    if (previous && previous !== element) this.silence(previous);
    return element;
  }

  private silence(element: MediaLike): void {
    element.pause();
    element.removeAttribute("src");
    element.load();
  }

  private wire<T extends MediaLike>(element: T): T {
    const mine = () => this.active === element;
    element.preload = "auto";
    element.addEventListener("playing", () => {
      if (!mine()) return;
      this.attempt = 0;
      this.emit({ status: "playing", error: null });
    });
    element.addEventListener("waiting", () => mine() && this.emit({ status: "loading" }));
    element.addEventListener("pause", () => {
      if (mine() && !this.wantPlaying && this.snapshot.status !== "error") this.emit({ status: "paused" });
    });
    element.addEventListener("ended", () => mine() && this.advance("ended"));
    element.addEventListener("picturechange", () => mine() && this.emit({ picture: (element as { hasPicture?: boolean }).hasPicture !== false }));
    element.addEventListener("timeupdate", () => {
      if (!mine()) return;
      const now = Date.now();
      if (now - this.lastTimeEmit < 1000) return;
      this.lastTimeEmit = now;
      const duration = Number.isFinite(element.duration) && element.duration > 0 ? element.duration : null;
      this.emit({ position: element.currentTime, duration });
    });
    element.addEventListener("error", () => mine() && this.handleError(element.error?.code ?? 0));
    element.addEventListener("trackinfo", (event) => {
      const info = (event as CustomEvent<YouTubeTrackInfo>).detail;
      const track = this.snapshot.track;
      if (mine() && track) this.emit({ track: { ...track, title: info.title || track.title, art: info.art || track.art } });
    });
    return element;
  }

  private handleError(code: number): void {
    const track = this.snapshot.track;
    if (!track || !this.wantPlaying) return;
    if (track.live && playbackProblem(track.url, `media_error_${code}`) !== "offline") {
      const delay = nextRetryDelay(this.attempt);
      if (delay !== null) {
        this.attempt += 1;
        this.emit({ status: "retrying" });
        this.clearRetry();
        this.retryTimer = setTimeout(() => this.load(track), delay);
        return;
      }
    }
    this.wantPlaying = false;
    this.emit({ status: "error", error: `media_error_${code}` });
    this.onError(`${trackSource(track)}:media_error_${code}`);
    if (!track.live && this.queue.entries.length > 1) this.advance("skip");
  }

  private clearRetry(): void {
    if (this.retryTimer !== null) clearTimeout(this.retryTimer);
    this.retryTimer = null;
  }

  private load(track: Track, position = 0): void {
    if (this.disposed) return;
    const generation = ++this.loadGeneration;
    this.pendingPosition = null;
    const audio = this.element(track);
    this.clearRetry();
    this.wantPlaying = true;
    this.emit({ track, status: "loading", error: null, position: 0, duration: null, video: this.showsVideo(track), picture: true });
    audio.src = track.url;
    audio.volume = this.volume * this.scale;
    if (position > 0 && !track.live) {
      audio.addEventListener("loadedmetadata", () => {
        if (generation !== this.loadGeneration || this.active !== audio) return;
        audio.currentTime = Number.isFinite(audio.duration) && audio.duration > 0 ? Math.min(position, Math.max(0, audio.duration - 1)) : position;
      }, { once: true });
    }
    void audio.play().catch(() => undefined);
  }

  playQueue(tracks: Track[], startIndex = 0, position = 0, videoMode = this.videoMode): void {
    if (tracks.length === 0) return;
    this.videoMode = videoMode;
    this.setQueue(playQueue.fromItems(this.queue, tracks, startIndex));
    this.attempt = 0;
    this.load(this.queue.entries[this.queue.position].item, position);
  }

  /** Adds to the queue; with nothing loaded the first added track starts. */
  enqueue(tracks: Track[], where: "end" | "next" = "end"): void {
    if (!tracks.length) return;
    const idle = !this.snapshot.track;
    this.setQueue(playQueue.enqueue(idle ? playQueue.clear(this.queue) : this.queue, tracks, where));
    if (idle) this.playPosition(0);
  }

  playEntry(key: string): void {
    const index = playQueue.indexOfKey(this.queue, key);
    if (index >= 0) this.playPosition(index);
  }

  removeEntry(key: string): void {
    const { state, currentChanged } = playQueue.remove(this.queue, key);
    this.setQueue(state);
    if (!currentChanged) return;
    const next = playQueue.current(state);
    if (next && this.wantPlaying) return this.load(next.item);
    if (!next) return this.stopAt(null);
    const active = this.active;
    this.active = null;
    if (active) this.silence(active);
    this.pendingPosition = 0;
    this.emit({ track: next.item, position: 0, duration: null, status: "paused" });
  }

  moveEntry(key: string, to: number): void {
    this.setQueue(playQueue.move(this.queue, key, to));
  }

  clearQueue(): void {
    const playing = playQueue.current(this.queue);
    this.setQueue(playing ? { ...this.queue, entries: [playing], position: 0, original: this.queue.shuffle ? [playing.key] : null } : playQueue.clear(this.queue));
  }

  setRepeat(repeat: RepeatMode): void {
    this.setQueue(playQueue.setRepeat(this.queue, repeat));
  }

  setShuffle(on: boolean): void {
    this.setQueue(playQueue.setShuffle(this.queue, on));
  }

  /** Puts a saved queue back exactly as it was, without mixing it again. */
  restoreQueue(tracks: Track[], startIndex: number, position: number, repeat: RepeatMode, shuffle: boolean): void {
    if (!tracks.length) return;
    const restored = playQueue.fromItems({ ...playQueue.emptyQueue<Track>(repeat), shuffle: false }, tracks, startIndex);
    this.setQueue({ ...restored, shuffle });
    this.attempt = 0;
    this.load(this.queue.entries[this.queue.position].item, position);
  }

  /** Repeat and shuffle chosen before anything plays, e.g. restored from settings. */
  setModes(repeat: RepeatMode, shuffle: boolean): void {
    this.setQueue({ ...playQueue.setShuffle(this.queue, shuffle), repeat });
  }

  private setQueue(queue: QueueState<Track>): void {
    this.queue = queue;
    this.emit({
      queue: queue.entries.map((entry) => ({ key: entry.key, track: entry.item })),
      queueIndex: queue.position,
      repeat: queue.repeat,
      shuffle: queue.shuffle,
    });
  }

  private playPosition(position: number): void {
    this.setQueue(playQueue.goTo(this.queue, position));
    this.attempt = 0;
    this.load(this.queue.entries[this.queue.position].item);
  }

  private advance(reason: "ended" | "skip"): void {
    const next = playQueue.nextPosition(this.queue, reason);
    if (next === null) return this.stopAt(this.snapshot.track);
    this.playPosition(next);
  }

  /** The queue ran out with repeat off: stay on the last track, paused at its start. */
  private stopAt(track: Track | null): void {
    this.wantPlaying = false;
    this.clearRetry();
    this.active?.pause();
    if (!track) {
      const active = this.active;
      this.active = null;
      if (active) this.silence(active);
    }
    this.pendingPosition = track ? 0 : null;
    this.emit({ track, status: track ? "paused" : "idle", position: 0, video: false });
  }

  checkpoint(): PlayerCheckpoint {
    return { queue: { ...this.queue, entries: this.queue.entries.map((e) => ({ key: e.key, item: { ...e.item } })) },
      snapshot: { ...this.snapshot, track: this.snapshot.track && { ...this.snapshot.track }, position: this.position() },
      playing: this.wantPlaying, videoMode: this.videoMode, scale: this.scale };
  }

  restore(saved: PlayerCheckpoint): void {
    if (this.disposed) return;
    this.loadGeneration++;
    this.clearRetry();
    this.wantPlaying = false;
    const active = this.active;
    this.active = null;
    if (active) this.silence(active);
    this.queue = { ...saved.queue, entries: saved.queue.entries.map((e) => ({ key: e.key, item: { ...e.item } })) };
    this.volume = saved.snapshot.volume;
    this.videoMode = saved.videoMode;
    this.scale = saved.scale;
    this.pendingPosition = saved.snapshot.track ? saved.snapshot.position : null;
    this.emit({ ...saved.snapshot });
    // Deferred loading also prevents autoplay from embedded providers when restoring a paused track.
    if (saved.playing && saved.snapshot.track) this.load(saved.snapshot.track, saved.snapshot.position);
  }

  next(): void {
    if (this.queue.entries.length === 0) return;
    if (this.stepList("next")) return;
    this.advance("skip");
  }

  previous(): void {
    if (this.queue.entries.length === 0) return;
    if (this.stepList("previous")) return;
    const previous = playQueue.previousPosition(this.queue);
    if (previous !== null) this.playPosition(previous);
  }

  private stepList(direction: "next" | "previous"): boolean {
    const track = this.snapshot.track;
    const engine = this.active === this.youtube ? this.youtube : this.active === this.video ? this.video : null;
    if (!track || !engine || !hasYouTubeList(track) || this.snapshot.status === "error") return false;
    this.wantPlaying = true;
    if (direction === "next") engine.nextVideo();
    else engine.previousVideo();
    return true;
  }

  private engineFor(track: Track): "video" | "youtube" | "audio" {
    if (this.createVideo && (this.showsVideo(track) || isHls(track.url) || parseEmbedStream(track.url))) return "video";
    return isYouTubeTrack(track) ? "youtube" : "audio";
  }

  private showsVideo(track: Track): boolean {
    return this.videoMode && !!this.createVideo && (track.kind === "video" || canShowVideo(track.url));
  }

  canShowVideo(): boolean {
    const track = this.snapshot.track;
    return !!this.createVideo && !!track && (track.kind === "video" || canShowVideo(track.url));
  }

  /** Moves the current track between hidden playback and the video window, keeping its place. */
  setVideoMode(on: boolean): void {
    if (this.videoMode === on) return;
    const track = this.snapshot.track;
    const position = this.position();
    const engineBefore = track ? this.engineFor(track) : null;
    this.videoMode = on;
    if (track && this.wantPlaying && engineBefore !== this.engineFor(track)) this.load(track, position);
    else this.emit({ video: !!track && this.showsVideo(track) });
  }

  setVideoBounds(bounds: VideoBounds): void {
    (this.video ??= this.createVideo ? this.wire(this.createVideo()) : null)?.setBounds(bounds);
  }

  setVideoVisible(visible: boolean): void {
    this.video?.setVisible(visible);
  }

  pause(): void {
    this.wantPlaying = false;
    this.clearRetry();
    this.active?.pause();
  }

  resume(): void {
    const track = this.snapshot.track;
    if (!track) return;
    if (!this.active || track.live || this.snapshot.status === "error") this.load(track, this.pendingPosition ?? 0);
    else {
      this.wantPlaying = true;
      void this.element(track).play().catch(() => undefined);
    }
  }

  /** Jumps within the current track; live streams have nowhere to go. */
  seekTo(seconds: number): void {
    const track = this.snapshot.track;
    if (!track || track.live) return;
    const duration = this.snapshot.duration ?? Number.POSITIVE_INFINITY;
    const target = Math.max(0, Math.min(seconds, duration - 1));
    if (this.active) this.active.currentTime = target;
    else this.pendingPosition = target;
    this.emit({ position: target });
  }

  setVolume(volume: number): void {
    this.volume = Math.max(0, Math.min(1, volume));
    if (this.active) this.active.volume = this.volume * this.scale;
    this.emit({ volume: this.volume });
  }

  setScale(scale: number): void {
    this.scale = Math.max(0, Math.min(1, scale));
    if (this.active) this.active.volume = this.volume * this.scale;
  }

  position(): number {
    return this.pendingPosition ?? (this.active && !this.snapshot.track?.live ? this.active.currentTime : 0);
  }

  get isPlaying(): boolean {
    return this.wantPlaying;
  }

  dispose(): void {
    this.disposed = true;
    this.clearRetry();
    this.wantPlaying = false;
    if (this.audio) this.silence(this.audio);
    this.youtube?.dispose();
    this.video?.dispose();
    this.audio = null;
    this.youtube = null;
    this.video = null;
    this.active = null;
    this.listeners.clear();
  }
}
