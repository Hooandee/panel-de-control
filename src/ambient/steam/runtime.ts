import { Navigation, findSP } from "@decky/ui";

import type { GameSessionPort } from "../../platform/gameSessions";
import { readFlag, writeFlag } from "../../platform/preferences";
import type { PowerPort, PowerSnapshot } from "../../platform/power";
import { arbitrate, conflictKey, type ArbiterDecision, type ThemeClaim, type ThirdPartySignal } from "../core/arbiter";
import { chooseBackground } from "../core/gameArtBlend";
import { motionFor, type MotionState } from "../core/powerPolicy";
import { needsCopy, videoTarget } from "../core/videoQuality";
import { gameVolumeTarget, planForGameState } from "../core/playbackPolicy";
import { advance, createRotation, shouldAdvance, type RotationState } from "../core/rotation";
import type { AmbientSettings, ClaimOwner, MediaKind, Channel, PlaylistContents, QueuedTrack, RadioCatalog, RadioFilters, RepeatMode, Station } from "../core/types";
import { AudioLoaderBridge } from "./audioLoader";
import { BackgroundLayer } from "./backgroundLayer";
import { GameMediaDirector, ThemeAudio, type GameMedia } from "./gameMedia";
import { installedGameAppIds, isStoreApp, libraryHeroUrl, neighborAppIdsIn, selectedAppIdIn } from "./librarySources";
import { linkKind, linkName } from "../core/linkName";
import { isLiveEmbed, parseEmbedStream } from "../core/streams";
import { parseYouTube } from "../core/youtube";
import { VideoFrameEngine, type VideoBounds } from "./videoFrame";
import { AmbientPlayer, trackSource, type PlayerCheckpoint, type PlayerSnapshot, type Track } from "./player";
import { currentSurface, subscribeSurface, type Surface } from "./route";
import * as rpc from "./rpc";
import { steamClass } from "./steamClasses";
import { AmbientThemeChannel } from "./themeChannel";
import { applyNeutralizer, detectThirdParty, readThemeClaim } from "./themeSignals";

export interface AmbientPorts {
  gameSessions: GameSessionPort;
  power: PowerPort;
  notify: (title: string, body: string) => void;
  translate: (key: string, vars?: Record<string, string>) => string;
}

export interface BackgroundItem {
  credit?: string;
  ref: string;
  kind: Exclude<MediaKind, "audio">;
  name: string;
  collection: string;
}

export interface LibraryMediaItem {
  ref: string;
  kind: MediaKind;
  name: string;
  collection: string;
}

interface LibrarySession {
  checkpoint: PlayerCheckpoint;
  station: Station | null;
  videoCollapsed: boolean;
  modified: boolean;
  request: number;
  saving: boolean;
}
type SettingsChange = (settings: AmbientSettings) => AmbientSettings;

export interface AmbientSnapshot {
  ready: boolean;
  state: rpc.AmbientState | null;
  scan: rpc.ScanResult | null;
  items: BackgroundItem[];
  /** One real image per collection for its tile, filled lazily. */
  previews: Record<string, string>;
  current: BackgroundItem | null;
  currentUrl: string | null;
  /** The rotation's current background, even while the game's art or a trailer covers it. */
  previewUrl: string | null;
  decision: ArbiterDecision;
  motion: MotionState;
  surface: Surface;
  optimizing: boolean;
  player: PlayerSnapshot;
  suggestedStations: Station[];
  selectedGame: { appid: string; name: string } | null;
  coveredBy: string[];
  inGame: boolean;
  /** The video window stays open and playing but is folded away, leaving the audio-only card. */
  videoCollapsed: boolean;
  videoFullscreen: boolean;
  /** The floating card holds the controller until the player leaves with B, Steam or QAM. */
  overlayControl: boolean;
  /** Panel's own Ambiente page is on screen, so the mini beside the QAM would repeat it. */
  pageOpen: boolean;
  libraryOpen: boolean;
  /** The media library dialog is on screen, on any tab; the floating card keeps out of its way. */
  libraryShown: boolean;
  /** Decky never rendered the floating player (its global components are not drawn on this install). */
  floatingMissing: boolean;
  error: string | null;
}

const ROTATION_TICK_MS = 5000;
const GAME_VOLUME_TICK_MS = 4000;
const SELECTION_TICK_MS = 400;
const TRAILER_MAX_HEIGHT = 360;
const CLAIM_CHECK_MS = 30000;
const POSITION_SAVE_MS = 15000;
const RESUME_TICK_MS = 2000;
const CACHE_RECONCILE_MS = 60000;
const QUEUE_SAVE_MS = 1500;
const EMPTY_QUEUE_VIEW: Pick<PlayerSnapshot, "queue" | "repeat" | "shuffle"> = { queue: [], repeat: "all", shuffle: false };
/** Right after a loader restart the backend can still be starting; the domain keeps asking instead of staying dark. */
const BACKEND_RETRY_MS = [3000, 10000, 30000];
// Themes remount (plugin reloads, CSS Loader resets) and reclaim a moment later; a painter only
// counts once it has stayed put this long with no claim change in between.
const SIGNAL_SETTLE_MS = 12000;
const RESUME_JUMP_MS = 10000;
const DAILY_FEEDS: Record<string, string> = { "suggested.nasa": "nasa-apod", "suggested.bing": "bing-daily" };
const VIDEO_URL = /\.(mp4|m4v|webm)(?:[?#].*)?$/i;

function spDocument(): Document | null {
  try {
    return findSP()?.document ?? null;
  } catch {
    return null;
  }
}

export function gameName(appid: string): string {
  try {
    const store = (globalThis as unknown as { appStore?: { GetAppOverviewByAppID?: (id: number) => { display_name?: string } | null } }).appStore;
    return store?.GetAppOverviewByAppID?.(Number(appid))?.display_name || appid;
  } catch {
    return appid;
  }
}

export function stationSubtitle(station: Station): string {
  return [station.country, station.tags[0], station.bitrate ? `${station.bitrate} kbps` : ""].filter(Boolean).join(", ");
}

export function favoriteToStation(favorite: { id: string; name: string; url: string; art?: string; subtitle?: string }): Station {
  return { id: favorite.id, name: favorite.name, url: favorite.url, favicon: favorite.art ?? "", country: favorite.subtitle ?? "", countryCode: "", tags: [], codec: "", bitrate: 0 };
}

function isVisual(kind: MediaKind): kind is BackgroundItem["kind"] {
  return kind === "image" || kind === "video";
}

/** Decky draws global components right after load; past this, the floating player is not coming. */
const FLOATING_CHECK_MS = 6000;

export class AmbientRuntime {
  private snapshot: AmbientSnapshot;
  private listeners = new Set<(s: AmbientSnapshot) => void>();
  private cleanups: (() => void)[] = [];
  private rotation: RotationState = createRotation("shuffle");
  private gameVolumeBusy = false;
  private gameVolumeLowered = false;
  private readonly gameMedia = new GameMediaDirector(
    (appid) => rpc.getAmbientGameMedia(appid, gameName(appid), isStoreApp(appid)),
    () => void this.render(),
    () => {
      const container = steamClass("RecentGamesContainer");
      const doc = spDocument();
      return doc && container ? neighborAppIdsIn(doc.querySelector(`.${container}`)) : [];
    },
  );
  private readonly themeAudio = new ThemeAudio(() => (typeof Audio === "function" ? new Audio() : null));
  private themePausedMusic = false;
  /** The game whose soundtrack and trailer sound stay quiet because the user chose their own music over it. */
  private themeSilencedFor: string | null = null;
  private lastSelectedAppId: string | null = null;
  private libraryViews = 0;
  private floatingMounts = 0;
  private videoPage: string | null = null;
  private lastAdvance = 0;
  private urls = new Map<string, string>();
  private pendingUrls = new Map<string, Promise<string | null>>();
  private noSpace = new Set<string>();
  private cacheGeneration = 0;
  private reconcilingCache = false;
  private feeds = new Map<string, rpc.RemoteImage[]>();
  private optimized = new Map<string, string>();
  /** A video too big for the screen stays on its first frame while its lighter copy is made. */
  private optimizingRef: string | null = null;
  private inGame = false;
  private power: PowerSnapshot = { battery: null };
  private thirdParty: ThirdPartySignal = { confidence: "none" };
  private themeClaim: ThemeClaim | null = null;
  private previousOwner: ClaimOwner | null = null;
  private toasted = new Set<string>();
  private currentStation: Station | null = null;
  private readonly layer: BackgroundLayer;
  private readonly player: AmbientPlayer;
  private readonly audioLoader = new AudioLoaderBridge();
  private stopped = false;
  private renderGeneration = 0;
  private mountRetries = 0;
  private mountRetryTimer: ReturnType<typeof setTimeout> | null = null;
  private backendRetryTimer: ReturnType<typeof setTimeout> | null = null;
  private backendRetries = 0;
  private queueSaveTimer: ReturnType<typeof setTimeout> | null = null;
  private savedQueue = "";
  private queueLoaded = false;
  private lastQueue: Pick<PlayerSnapshot, "queue" | "repeat" | "shuffle"> = EMPTY_QUEUE_VIEW;
  private saveChain: Promise<void> = Promise.resolve();
  private saveSequence = 0;
  private librarySession: LibrarySession | null = null;

  private claimChangedAt = Date.now();
  private pendingPainter: { id: string; since: number } | null = null;
  private signalTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private readonly ports: AmbientPorts,
    private readonly channel: AmbientThemeChannel = new AmbientThemeChannel(),
    private readonly signalSettleMs = SIGNAL_SETTLE_MS,
  ) {
    this.layer = new BackgroundLayer(spDocument, (url, _w, height) => this.maybeOptimize(url, height));
    this.channel.setFrameSource(() => this.layer.activeMedia());
    this.player = new AmbientPlayer(
      undefined,
      (detail) => void rpc.recordAmbientEvent(detail.startsWith("radio") ? "radio_error" : "playback_error", detail).catch(() => undefined),
      undefined,
      () => new VideoFrameEngine(() => rpc.getAmbientVideoPage(), () => spDocument()),
    );
    this.snapshot = {
      ready: false,
      state: null,
      scan: null,
      items: [],
      previews: {},
      current: null,
      currentUrl: null,
      previewUrl: null,
      decision: { background: "panel", music: "panel", conflict: null },
      motion: "play",
      surface: currentSurface(),
      optimizing: false,
      player: this.player.getSnapshot(),
      suggestedStations: [],
      selectedGame: null,
      coveredBy: [],
      inGame: false,
      videoCollapsed: false,
      videoFullscreen: false,
      overlayControl: false,
      pageOpen: false,
      libraryOpen: false,
      libraryShown: false,
      floatingMissing: false,
      error: null,
    };
  }


  async start(): Promise<void> {
    const floatingCheck = setTimeout(() => {
      if (this.stopped || this.floatingMounts > 0) return;
      this.patch({ floatingMissing: true });
      void rpc.recordAmbientEvent("floating_missing", "decky_global_components_not_rendered").catch(() => undefined);
    }, FLOATING_CHECK_MS);
    this.cleanups.push(() => clearTimeout(floatingCheck));
    this.cleanups.push(this.player.subscribe((player) => {
      if (!player.video && this.snapshot.videoFullscreen) this.setVideoFullscreen(false);
      this.patch({ player });
      this.scheduleQueueSave(player);
    }));
    this.cleanups.push(this.channel.onClaimsChanged(() => {
      this.claimChangedAt = Date.now();
      this.checkSignals();
      void this.render();
    }));
    this.cleanups.push(this.ports.gameSessions.subscribe((game) => this.onGame(game !== null)));
    this.cleanups.push(this.ports.power.subscribe((power) => {
      this.power = power;
      this.render();
    }));
    this.cleanups.push(subscribeSurface((surface) => {
      const returnedHome = surface === "home" && this.snapshot.surface !== "home";
      this.patch({ surface });
      if (returnedHome && this.settings()?.background.onReturnHome) this.advanceRotation();
      this.checkSignals();
      this.render();
    }));
    const rotationTimer = setInterval(() => this.tickRotation(), ROTATION_TICK_MS);
    const claimTimer = setInterval(() => this.checkSignals(), CLAIM_CHECK_MS);
    const positionTimer = setInterval(() => this.savePosition(), POSITION_SAVE_MS);
    const gameVolumeTimer = setInterval(() => this.syncGameVolume(), GAME_VOLUME_TICK_MS);
    const selectionTimer = setInterval(() => this.watchSelection(), SELECTION_TICK_MS);
    const cacheTimer = setInterval(() => void this.reconcileCache(), CACHE_RECONCILE_MS);
    let lastTick = Date.now();
    const resumeTimer = setInterval(() => {
      const now = Date.now();
      if (now - lastTick > RESUME_JUMP_MS) {
        this.layer.repaint();
        setTimeout(() => this.layer.repaint(), 1500);
      }
      lastTick = now;
    }, RESUME_TICK_MS);
    this.cleanups.push(() => {
      clearInterval(resumeTimer);
      clearInterval(rotationTimer);
      clearInterval(claimTimer);
      clearInterval(positionTimer);
      clearInterval(gameVolumeTimer);
      clearInterval(selectionTimer);
      clearInterval(cacheTimer);
    });
    this.inGame = this.ports.gameSessions.current() !== null;
    this.patch({ inGame: this.inGame });
    if (!await this.reconcileCache()) await this.reload();
    if (this.stopped) return;
    const settings = this.settings();
    if (settings) {
      this.savedQueue = queueSignature(settings.music.queue, settings.music.repeat, settings.music.shuffle);
      this.player.setModes(settings.music.repeat, settings.music.shuffle);
    }
    if (settings?.music.enabled && planForGameState(this.inGame, settings.music.inGameMediaLevel).playing) void this.startMusic();
  }

  stop(): void {
    this.stopped = true;
    this.librarySession = null;
    this.savePosition();
    this.gameMedia.dispose();
    this.themeAudio.stop();
    for (const cleanup of this.cleanups.splice(0)) cleanup();
    if (this.mountRetryTimer !== null) clearTimeout(this.mountRetryTimer);
    if (this.backendRetryTimer !== null) clearTimeout(this.backendRetryTimer);
    if (this.queueSaveTimer !== null) clearTimeout(this.queueSaveTimer);
    if (this.signalTimer !== null) clearTimeout(this.signalTimer);
    this.layer.dispose();
    this.channel.reset();
    const doc = spDocument();
    if (doc) applyNeutralizer(doc, []);
    spDocument()?.documentElement.removeAttribute("data-pdc-ambient-background");
    this.audioLoader.restore();
    this.player.dispose();
    this.listeners.clear();
  }

  subscribe(listener: (s: AmbientSnapshot) => void): () => void {
    this.listeners.add(listener);
    listener(this.snapshot);
    return () => this.listeners.delete(listener);
  }

  getSnapshot(): AmbientSnapshot {
    return this.snapshot;
  }

  private patch(patch: Partial<AmbientSnapshot>): void {
    this.snapshot = { ...this.snapshot, ...patch };
    for (const listener of this.listeners) listener(this.snapshot);
  }

  private settings(): AmbientSettings | null {
    return this.snapshot.state?.settings ?? null;
  }


  async reload(retry = true): Promise<void> {
    if (retry) {
      if (this.noSpace.size > 0) this.layer.dispose();
      this.noSpace.clear();
    }
    try {
      const [state, scan] = await Promise.all([rpc.getAmbientState(), rpc.scanAmbientSources()]);
      if (this.stopped) return;
      this.rotation = createRotation(state.settings.background.order);
      this.patch({ state, scan, ready: true, error: this.noSpace.size ? "no_space" : null });
      this.backendRetries = 0;
      await this.rebuildItems();
      this.checkSignals();
      this.advanceRotation();
    } catch {
      if (this.stopped) return;
      this.patch({ ready: true, error: "backend_unavailable" });
      this.retryBackend();
    }
  }

  private retryBackend(): void {
    if (this.backendRetryTimer !== null) return;
    const delay = BACKEND_RETRY_MS[Math.min(this.backendRetries, BACKEND_RETRY_MS.length - 1)];
    this.backendRetries++;
    this.backendRetryTimer = setTimeout(() => {
      this.backendRetryTimer = null;
      if (!this.stopped) void this.reload();
    }, delay);
  }

  private clearMediaCache(): void {
    this.cacheGeneration++;
    this.urls.clear();
    this.pendingUrls.clear();
    this.optimized.clear();
    this.previewRequests.clear();
    this.patch({ previews: {}, currentUrl: null, previewUrl: null });
  }

  private async reconcileCache(): Promise<boolean> {
    if (this.stopped || this.inGame || this.reconcilingCache) return false;
    this.reconcilingCache = true;
    try {
      if (!await rpc.reconcileAmbientCache() || this.stopped) return false;
      this.clearMediaCache();
      await this.reload(false);
      return true;
    } catch {
      return false;
    } finally {
      this.reconcilingCache = false;
    }
  }

  private reportNoSpace(key: string): void {
    const first = this.noSpace.size === 0;
    this.noSpace.add(key);
    this.patch({ error: "no_space" });
    if (first) this.ports.notify(this.ports.translate("ambient.bg.title"), this.ports.translate("ambient.error.noSpace"));
  }

  private async feed(collection: string): Promise<rpc.RemoteImage[]> {
    const source = DAILY_FEEDS[collection];
    if (!source) return [];
    const cached = this.feeds.get(collection);
    if (cached) return cached;
    const market = typeof navigator !== "undefined" ? navigator.language : "en-US";
    const items = await rpc.getAmbientRemoteFeed(source, market).catch((error) => {
      if (collection === "suggested.nasa") throw error;
      return [] as rpc.RemoteImage[];
    });
    if (collection === "suggested.nasa" && !items.length) throw new Error("nasa_unavailable");
    this.feeds.set(collection, items);
    return items;
  }

  async libraryItems(collection: string): Promise<BackgroundItem[]> {
    if (collection === "suggested.library") return installedGameAppIds().map((appid) => ({ ref: `steam:${appid}`, kind: "image", name: gameName(String(appid)), collection }));
    if (collection in DAILY_FEEDS) return (await this.feed(collection)).map((image) => ({ ref: `remote:${image.url}`, kind: "image", name: image.title, collection, ...(collection === "suggested.nasa" && image.credit ? { credit: image.credit } : {}) }));
    const settings = this.settings();
    const favorite = [...settings?.collections.favorites ?? [], ...settings?.radio.favorites ?? []].find((f) => f.id === collection);
    if (favorite) return [{ ref: `remote:${favorite.url}`, kind: VIDEO_URL.test(favorite.url) ? "video" : "image", name: favorite.name, collection }];
    const scan = this.snapshot.scan;
    return (scan?.library?.[collection] ?? scan?.collections[collection] ?? []).flatMap((media) => isVisual(media.kind) ? [{ ref: media.id, kind: media.kind, name: media.name, collection }] : []);
  }

  previewMedia(ref: string): Promise<string | null> {
    if (ref.startsWith("remote:")) return Promise.resolve(ref.slice(7));
    return this.resolve(ref);
  }

  async useBackground(item: BackgroundItem, persist: (change: SettingsChange) => Promise<void> = (change) => this.updateSettings(change)): Promise<void> {
    await persist((s) => ({ ...s, background: { ...s.background, enabled: true, pinned: item.ref, selectedRefs: [], collections: [...new Set([...s.background.collections, item.collection])] } }));
    this.advanceRotation();
    if (this.snapshot.error === "save_failed") throw new Error("save_failed");
  }

  async useBackgroundSelection(items: BackgroundItem[], persist: (change: SettingsChange) => Promise<void> = (change) => this.updateSettings(change)): Promise<void> {
    const photos = items.filter((item) => item.kind === "image");
    const selectedRefs = [...new Set(photos.map((item) => item.ref))];
    if (selectedRefs.length < 2) throw new Error("selection_requires_two_photos");
    await persist((s) => ({ ...s, background: {
      ...s.background, enabled: true, pinned: "", selectedRefs,
      collections: [...new Set([...s.background.collections, ...photos.map((item) => item.collection).filter(Boolean)])],
    } }));
    if (this.snapshot.error === "save_failed") throw new Error("save_failed");
  }

  markFloatingMounted(): () => void {
    this.floatingMounts += 1;
    if (this.snapshot.floatingMissing) this.patch({ floatingMissing: false });
    return () => {
      this.floatingMounts -= 1;
    };
  }

  showLibrary(): () => void {
    this.libraryViews += 1;
    this.patch({ libraryShown: true });
    let shown = true;
    return () => {
      if (!shown) return;
      shown = false;
      this.libraryViews -= 1;
      this.patch({ libraryShown: this.libraryViews > 0 });
    };
  }

  beginLibrarySession(): () => void {
    if (this.librarySession) this.finishLibrarySession(this.librarySession, true);
    const session: LibrarySession = { checkpoint: this.player.checkpoint(), station: this.currentStation, videoCollapsed: this.snapshot.videoCollapsed, modified: false, request: 0, saving: false };
    this.librarySession = session;
    this.stopOverlayControl();
    this.patch({ libraryOpen: true });
    void this.render();
    void this.refreshScan();
    return () => this.finishLibrarySession(session, true);
  }

  /** Files copied since the last scan (from desktop mode, a USB stick) show up when the library opens. */
  private async refreshScan(): Promise<void> {
    const scan = await rpc.scanAmbientSources().catch(() => null);
    if (!scan || this.stopped) return;
    this.patch({ scan });
    await this.rebuildItems();
  }

  private captureLibraryPlayback(): void {
    const session = this.librarySession;
    if (!session || session.modified) return;
    session.checkpoint = this.player.checkpoint();
    session.station = this.currentStation;
    session.videoCollapsed = this.snapshot.videoCollapsed;
    session.modified = true;
  }

  private finishLibrarySession(session: LibrarySession, restore: boolean): void {
    if (this.librarySession !== session) return;
    session.request++;
    if (restore && session.modified) {
      this.currentStation = session.station;
      this.player.restore(session.checkpoint);
      const settings = this.settings();
      if (settings) {
        const plan = planForGameState(this.inGame, settings.music.inGameMediaLevel);
        this.player.setScale(plan.volumeScale);
        if (!plan.playing) this.player.pause();
      }
    }
    this.librarySession = null;
    this.patch({ libraryOpen: false, videoCollapsed: restore ? session.videoCollapsed : this.snapshot.videoCollapsed, videoFullscreen: false, overlayControl: false });
    this.lastQueue = EMPTY_QUEUE_VIEW;
    this.scheduleQueueSave(this.player.getSnapshot());
    if (restore) console.info("[Ambient library] cancel");
    void this.render();
  }

  private async libraryTrack(item: LibraryMediaItem): Promise<Track> {
    if (item.kind === "image") throw new Error("image_has_no_playback");
    const url = await this.previewMedia(item.ref);
    if (!url) throw new Error("media_unavailable");
    const embed = parseEmbedStream(url);
    return { id: item.ref, title: item.name, subtitle: "", art: "", url, live: embed ? isLiveEmbed(embed) : false, kind: item.kind };
  }

  async previewLibraryMedia(item: LibraryMediaItem): Promise<void> {
    const session = this.librarySession;
    if (!session || session.saving || item.kind === "image") return;
    const request = ++session.request;
    try {
      const track = await this.libraryTrack(item);
      if (this.librarySession !== session || request !== session.request || this.stopped) return;
      this.captureLibraryPlayback();
      this.currentStation = null;
      this.themeAudio.stop();
      this.player.playQueue([track], 0, 0, item.kind === "video");
      this.patch({ videoCollapsed: false });
      console.info(`[Ambient library] preview:${item.kind}`);
      void this.render();
    } catch (error) {
      if (this.librarySession !== session || request !== session.request) return;
      void rpc.recordAmbientEvent("playback_error", "library preview failed").catch(() => undefined);
      throw error;
    }
  }

  private async saveLibrarySettings(session: LibrarySession, change: SettingsChange): Promise<void> {
    const save = this.saveChain.then(async () => {
      const state = this.snapshot.state;
      if (!state || this.librarySession !== session || this.stopped) throw new Error("library_closed");
      const saved = await rpc.saveAmbientSettings(change(state.settings));
      if (this.librarySession !== session || this.stopped) {
        await rpc.saveAmbientSettings(this.settings() ?? state.settings);
        throw new Error("library_closed");
      }
      this.patch({ state: { ...state, settings: saved }, error: null });
      await this.rebuildItems();
      if (this.librarySession !== session || this.stopped) {
        await rpc.saveAmbientSettings(state.settings);
        this.patch({ state });
        await this.rebuildItems();
        throw new Error("library_closed");
      }
      if (saved.background.pinned !== state.settings.background.pinned ||
        (saved.background.selectedRefs ?? []).join() !== (state.settings.background.selectedRefs ?? []).join()) this.advanceRotation();
    });
    this.saveChain = save.then(() => undefined, () => undefined);
    await save;
  }

  async saveLibrarySelection(items: LibraryMediaItem[], purpose: "background" | "playback"): Promise<void> {
    const session = this.librarySession;
    if (!session || session.saving || !items.length) throw new Error("library_selection_unavailable");
    session.saving = true;
    session.request++;
    try {
      if (purpose === "background") {
        const visuals = items.filter((item): item is BackgroundItem => item.kind !== "audio");
        if (visuals.length !== items.length) throw new Error("invalid_background_selection");
        const persist = (change: SettingsChange) => this.saveLibrarySettings(session, change);
        if (visuals.length === 1) await this.useBackground(visuals[0], persist);
        else await this.useBackgroundSelection(visuals, persist);
      } else {
        if (items.length > 1) {
          const tracks = await this.tracksFor(items);
          if (this.librarySession !== session) throw new Error("library_closed");
          if (!tracks.length) throw new Error("media_unavailable");
          this.playTracks(tracks);
          console.info(`[Ambient library] save:${purpose}`);
          this.finishLibrarySession(session, false);
          return;
        }
        const item = items[0];
        const track = await this.libraryTrack(item);
        if (this.librarySession !== session) throw new Error("library_closed");
        const same = this.player.getSnapshot().track?.id === item.ref;
        const position = same ? this.player.position() : 0;
        await this.saveLibrarySettings(session, (s) => ({ ...s, music: { ...s.music, enabled: same ? this.player.isPlaying : true, source: "music", volume: this.player.getSnapshot().volume, videoOn: same ? this.player.getSnapshot().video : item.kind === "video", lastTrack: { id: item.ref, position } } }));
        if (this.librarySession !== session) throw new Error("library_closed");
        this.currentStation = null;
        if (!same) this.player.playQueue([track], 0, 0, item.kind === "video");
      }
      if (this.librarySession !== session) throw new Error("library_closed");
      console.info(`[Ambient library] save:${purpose}`);
      this.finishLibrarySession(session, purpose === "background");
    } catch (error) {
      if (this.librarySession === session) {
        this.patch({ error: "save_failed" });
        void rpc.recordAmbientEvent("playback_error", "library save failed").catch(() => undefined);
      }
      throw error;
    } finally { session.saving = false; }
  }

  private async rebuildItems(): Promise<void> {
    const settings = this.settings();
    if (!settings) return;
    const selected = settings.background.selectedRefs;
    if (selected?.length) {
      const available = new Map(this.snapshot.items.map((item) => [item.ref, item]));
      for (const [collection, media] of Object.entries(this.snapshot.scan?.library ?? this.snapshot.scan?.collections ?? {})) {
        for (const item of media) if (item.kind === "image") available.set(item.id, { ref: item.id, name: item.name, kind: "image", collection });
      }
      this.patch({ items: selected.map((ref) => available.get(ref) ?? { ref, kind: "image", name: ref, collection: "" }) });
      return;
    }
    const items: BackgroundItem[] = [];
    for (const collection of settings.background.collections) {
      const available = await this.libraryItems(collection).catch((error) => {
        if (collection === "suggested.nasa") return [];
        throw error;
      });
      items.push(...available);
    }
    this.patch({ items });
  }

  private previewRequests = new Set<string>();

  /** Picks each collection's first image for its tile: a library hero, a daily photo, a file. */
  loadPreviews(): void {
    const state = this.snapshot.state;
    if (!state) return;
    for (const entry of state.collections) {
      if (this.previewRequests.has(entry.id)) continue;
      this.previewRequests.add(entry.id);
      void this.previewFor(entry.id, entry.url).then((url) => {
        if (!url) this.previewRequests.delete(entry.id);
        else if (!this.stopped) this.patch({ previews: { ...this.snapshot.previews, [entry.id]: url } });
      });
    }
  }

  private async previewFor(id: string, url?: string): Promise<string | null> {
    if (id === "suggested.library") {
      const appid = installedGameAppIds()[0];
      return appid ? libraryHeroUrl(appid) : null;
    }
    if (id in DAILY_FEEDS) return (await this.feed(id).catch(() => []))[0]?.url ?? null;
    if (url) return VIDEO_URL.test(url) ? null : url;
    const image = this.snapshot.scan?.collections[id]?.find((m) => m.kind === "image");
    return image ? this.resolve(image.id) : null;
  }

  private async resolve(ref: string): Promise<string | null> {
    const effective = this.optimized.get(`${ref}|${this.settings()?.background.videoQuality ?? "fluid"}`) ?? ref;
    const cached = this.urls.get(effective);
    if (cached) return cached;
    if (this.noSpace.has(effective)) return null;
    const pending = this.pendingUrls.get(effective);
    if (pending) return pending;
    const generation = this.cacheGeneration;
    const request = (async () => {
      let url: string | null = null;
      if (effective.startsWith("steam:")) url = libraryHeroUrl(effective.slice(6));
      else if (effective.startsWith("remote:")) {
        const collection = this.snapshot.items.find((item) => item.ref === ref)?.collection ?? "";
        const served = await rpc.cacheAmbientRemote(effective.slice(7), collection).catch(() => ({ error: "unreachable" }) as rpc.Served);
        if (this.stopped || generation !== this.cacheGeneration) return null;
        if ("error" in served && served.error === "no_space") this.reportNoSpace(effective);
        url = "url" in served ? served.url : null;
      } else url = await rpc.getAmbientMediaUrl(effective).catch(() => null);
      if (this.stopped || generation !== this.cacheGeneration) return null;
      if (url) this.urls.set(effective, url);
      return url;
    })();
    this.pendingUrls.set(effective, request);
    try { return await request; }
    finally { if (this.pendingUrls.get(effective) === request) this.pendingUrls.delete(effective); }
  }


  private tickRotation(): void {
    const settings = this.settings();
    if (!settings || this.snapshot.motion !== "play" || this.pinnedItem()) return;
    if (shouldAdvance(Date.now() - this.lastAdvance, settings.background.intervalSec, false, settings.background.onReturnHome)) this.advanceRotation();
  }

  private setCurrent(item: BackgroundItem | null): void {
    this.patch({ current: item });
    if (!item) return this.patch({ previewUrl: null });
    void this.resolve(item.ref).then((url) => {
      if (this.snapshot.current?.ref === item.ref) this.patch({ previewUrl: url ?? null });
    });
  }

  private pinnedItem(): BackgroundItem | null {
    const pinned = this.settings()?.background.pinned;
    return pinned ? this.snapshot.items.find((i) => i.ref === pinned) ?? null : null;
  }

  advanceRotation(): void {
    const items = this.snapshot.items;
    const pinned = this.pinnedItem();
    if (pinned) {
      this.setCurrent(pinned);
      void this.render();
      return;
    }
    this.rotation = advance(this.rotation, items.map((i) => i.ref));
    this.lastAdvance = Date.now();
    const current = items.find((i) => i.ref === this.rotation.current) ?? null;
    this.setCurrent(current);
    void this.render();
  }

  /** Browses the backgrounds one by one; when a single one is kept, the one reached becomes it. */
  stepBackground(direction: 1 | -1): void {
    const items = this.snapshot.items;
    if (items.length === 0) return;
    const index = items.findIndex((i) => i.ref === this.snapshot.current?.ref);
    const next = items[(index + direction + items.length) % items.length];
    this.rotation = { ...this.rotation, current: next.ref };
    this.lastAdvance = Date.now();
    this.setCurrent(next);
    if (this.settings()?.background.pinned) void this.updateSettings((s) => ({ ...s, background: { ...s.background, pinned: next.ref } }));
    else void this.render();
  }

  setPinned(pinned: boolean): Promise<void> {
    const ref = pinned ? this.snapshot.current?.ref ?? this.snapshot.items[0]?.ref ?? "" : "";
    return this.updateSettings((s) => ({ ...s, background: { ...s.background, pinned: ref } }));
  }

  private selectedAppId(doc: Document | null): string | null {
    const container = steamClass("RecentGamesContainer");
    return doc && container ? selectedAppIdIn(doc.querySelector(`.${container}`)) : null;
  }


  private async render(): Promise<void> {
    const settings = this.settings();
    const doc = spDocument();
    if (!settings || this.stopped) return;
    const generation = ++this.renderGeneration;
    const backgroundOn = settings.background.enabled;
    const decision = arbitrate({
      themeClaims: backgroundOn && this.themeClaim ? [this.themeClaim] : [],
      thirdParty: backgroundOn ? this.thirdParty : { confidence: "none" },
      audioLoader: settings.music.enabled && this.audioLoader.isActive(),
      claims: settings.claims,
      previous: this.previousOwner,
    });
    this.announce(decision);
    const surface = this.snapshot.surface;
    const surfaceAllowed = surface === "home" || (surface === "library" && settings.background.library);
    const motion = motionFor({
      inGame: this.inGame,
      screenOn: doc?.visibilityState !== "hidden",
      surfaceVisible: surfaceAllowed,
      battery: this.power.battery,
      threshold: settings.background.lowBatteryPercent,
    });
    this.patch({ decision, motion });
    this.syncMusicOwnership(decision, settings);

    const owns = settings.background.enabled && decision.background === "panel";
    const selectedAppId = this.selectedAppId(doc);
    if (selectedAppId) {
      if (selectedAppId !== this.themeSilencedFor) this.themeSilencedFor = null;
      this.lastSelectedAppId = selectedAppId;
    }
    if (selectedAppId !== this.snapshot.selectedGame?.appid) {
      this.patch({ selectedGame: selectedAppId ? { appid: selectedAppId, name: gameName(selectedAppId) } : null });
    }
    const wantsTrailers = settings.background.enabled && settings.background.gameTrailers;
    const wantsGameMedia = wantsTrailers || settings.background.gameThemes;
    this.gameMedia.select(wantsGameMedia && surface === "home" && !this.inGame && motion === "play" ? selectedAppId : null);
    const settled = this.gameMedia.current();
    const trailerSound = this.syncGameTheme(settled && settled.appid !== this.themeSilencedFor ? settled.media : null, settings);
    const trailer = wantsTrailers ? settled?.media.trailer ?? null : null;
    if (trailer && owns) {
      const page = await this.trailerPage(trailer.url, trailerSound ? Math.round(settings.music.volume * 100) : 0);
      if (this.stopped || generation !== this.renderGeneration) return;
      if (page && this.layer.apply({ url: page, kind: "page" }, { transition: "fade", nativeArt: "hide", motion, visible: true })) {
        doc?.documentElement.setAttribute("data-pdc-ambient-background", "panel");
        return;
      }
    }
    // Until the trailer is ready the selected game shows its own background, or Steam's art for it.
    const artMode = wantsTrailers && this.gameMedia.pending() ? "game" : settings.background.gameArt;
    const choice = chooseBackground(artMode, this.snapshot.current?.ref ?? null, selectedAppId, settings.background.perGame);
    if (!owns || choice.mediaRef === null) {
      this.layer.apply(null, { transition: settings.background.transition, nativeArt: "show", motion, visible: false });
      doc?.documentElement.removeAttribute("data-pdc-ambient-background");
      this.channel.publish({ owner: "theme", media: null, motion });
      if (doc) applyNeutralizer(doc, []);
      this.patch({ coveredBy: [] });
      this.previousOwner = decision.background === "panel" && !owns ? null : decision.background;
      this.patch({ currentUrl: null });
      return;
    }
    const url = await this.resolve(choice.mediaRef);
    if (this.stopped || generation !== this.renderGeneration || !url) return;
    const kind = this.snapshot.items.find((i) => i.ref === choice.mediaRef)?.kind ?? (VIDEO_URL.test(url) ? "video" : "image");
    this.channel.publish({ owner: "panel", media: { url, kind }, motion });
    const hostClaim = this.channel.activeClaim();
    if (hostClaim?.mode === "host" && surface !== "other" && hostClaim.surfaces.includes(surface)) {
      this.layer.apply(null, { transition: settings.background.transition, nativeArt: "show", motion, visible: false });
      if (doc) applyNeutralizer(doc, []);
      doc?.documentElement.setAttribute("data-pdc-ambient-background", "panel");
      this.previousOwner = "panel";
      this.patch({ currentUrl: url });
      return;
    }
    const chosen = Object.entries(settings.claims).filter(([id, owner]) => id.startsWith("css:") && owner === "panel").map(([id]) => id);
    if (doc) applyNeutralizer(doc, chosen);
    const coveredBy = this.thirdParty.confidence === "low" ? (this.thirdParty.candidates ?? []).filter((id) => !chosen.includes(id)) : [];
    if (coveredBy.join() !== this.snapshot.coveredBy.join()) this.patch({ coveredBy });
    const shown = this.layer.apply({ url, kind }, {
      transition: settings.background.transition,
      nativeArt: choice.nativeArt,
      motion: motion === "play" && this.optimizingRef === choice.mediaRef ? "pause" : motion,
      visible: surfaceAllowed,
    });
    if (shown) {
      doc?.documentElement.setAttribute("data-pdc-ambient-background", "panel");
      this.previousOwner = "panel";
      this.mountRetries = 0;
    } else if (surfaceAllowed) this.retryMount();
    this.patch({ currentUrl: url });
  }

  /** The selected game changes without any route event; notice it while game media is wanted. */
  private watchSelection(): void {
    const settings = this.settings();
    if (!settings || this.inGame || this.snapshot.surface !== "home") return;
    if (!settings.background.gameTrailers && !settings.background.gameThemes && Object.keys(settings.background.perGame).length === 0) return;
    if (this.selectedAppId(spDocument()) !== (this.snapshot.selectedGame?.appid ?? null)) void this.render();
  }

  /**
   * The game's soundtrack replaces Ambiente's media while its game is selected; without one, the
   * trailer's own audio does. Returns whether the trailer should sound.
   */
  private syncGameTheme(media: GameMedia | null, settings: AmbientSettings): boolean {
    if (this.librarySession) {
      this.themeAudio.stop();
      return false;
    }
    const wanted = settings.background.gameThemes ? media : null;
    const theme = wanted?.theme ?? null;
    const trailerSound = !theme && !!wanted?.trailer && settings.background.enabled && settings.background.gameTrailers;
    if (theme) this.themeAudio.play(theme.url, settings.music.volume);
    else this.themeAudio.stop();
    const sounding = !!theme || trailerSound;
    if (sounding && !this.themePausedMusic && this.player.isPlaying) {
      this.themePausedMusic = true;
      this.player.pause();
    } else if (!sounding && this.themePausedMusic) {
      this.themePausedMusic = false;
      this.player.resume();
    }
    return trailerSound;
  }

  private async trailerPage(stream: string, volume: number): Promise<string | null> {
    this.videoPage ??= await rpc.getAmbientVideoPage().catch(() => null);
    if (!this.videoPage) return null;
    const params = new URLSearchParams({ src: stream, vol: String(volume), loop: "1", maxh: String(TRAILER_MAX_HEIGHT) });
    return `${this.videoPage}?${params.toString()}`;
  }

  /** Steam renders BasicHome after the route changes; try again shortly instead of waiting a rotation. */
  private retryMount(): void {
    if (this.mountRetryTimer !== null || this.mountRetries >= 12) return;
    this.mountRetries += 1;
    this.mountRetryTimer = setTimeout(() => {
      this.mountRetryTimer = null;
      void this.render();
    }, 250);
  }

  private announce(decision: ArbiterDecision): void {
    const key = conflictKey(decision.conflict);
    if (!key || this.toasted.has(key) || !decision.conflict) return;
    this.toasted.add(key);
    const remembered = `pdc:ambient:toasted:${key}`;
    if (readFlag(remembered, false)) return;
    writeFlag(remembered, true);
    const { conflict } = decision;
    const t = this.ports.translate;
    const title = conflict.kind === "theme"
      ? t("ambient.toast.theme", { name: conflict.name ?? "" })
      : conflict.kind === "music" ? t("ambient.toast.music") : t("ambient.toast.other");
    this.ports.notify(title, t("ambient.toast.body"));
    void rpc.recordAmbientEvent("conflict", key).catch(() => undefined);
  }

  private checkSignals(): void {
    const doc = spDocument();
    if (!doc) return;
    const runtimeClaim = this.channel.activeClaim();
    this.themeClaim = runtimeClaim ? { id: runtimeClaim.themeId, name: runtimeClaim.name } : readThemeClaim(doc);
    const signal: ThirdPartySignal = this.themeClaim ? { confidence: "none" } : detectThirdParty(doc);
    this.thirdParty = this.settledPainter(signal);
  }

  /** Doubt stays silent: a painter must persist, with no theme claiming or releasing meanwhile. */
  private settledPainter(signal: ThirdPartySignal): ThirdPartySignal {
    if (signal.confidence === "none" || !signal.id) {
      this.pendingPainter = null;
      return { confidence: "none" };
    }
    const now = Date.now();
    const since = Math.max(this.claimChangedAt, this.pendingPainter?.id === signal.id ? this.pendingPainter.since : now);
    this.pendingPainter = { id: signal.id, since };
    if (now - since >= this.signalSettleMs) return signal;
    if (this.signalTimer === null) {
      this.signalTimer = setTimeout(() => {
        this.signalTimer = null;
        this.checkSignals();
        void this.render();
      }, this.signalSettleMs - (now - since) + 50);
    }
    return { confidence: "none" };
  }

  private maybeOptimize(url: string, height: number): void {
    const settings = this.settings();
    const current = this.snapshot.current;
    const view = spDocument()?.defaultView;
    const screenHeight = Math.round((view?.innerHeight ?? 800) * (view?.devicePixelRatio ?? 1));
    if (!settings?.background.optimizeVideos || !current || current.kind !== "video") return;
    const quality = settings.background.videoQuality;
    const target = videoTarget(quality, screenHeight);
    const key = `${current.ref}|${quality}`;
    if (!current.ref.startsWith("local:") || this.optimized.has(key) || this.noSpace.has(key) || !needsCopy(quality, height, target)) return;
    if (this.snapshot.optimizing || this.urls.get(current.ref) !== url) return;
    this.patch({ optimizing: true });
    this.optimizingRef = current.ref;
    const generation = this.cacheGeneration;
    void this.render();
    void rpc.optimizeAmbientMedia(current.ref, target.height, target.fps)
      .then((result) => {
        if (this.stopped || generation !== this.cacheGeneration) return;
        if ("id" in result) {
          this.optimized.set(key, result.id);
          if (this.snapshot.current?.ref === current.ref) void this.render();
        } else if (result.error === "no_space") this.reportNoSpace(key);
      })
      .catch(() => undefined)
      .finally(() => {
        this.optimizingRef = null;
        this.patch({ optimizing: false });
        void this.render();
      });
  }


  private syncMusicOwnership(decision: ArbiterDecision, settings: AmbientSettings): void {
    if (decision.music !== "panel") {
      if (this.player.isPlaying) this.player.pause();
      this.audioLoader.restore();
      return;
    }
    if (this.player.isPlaying) this.audioLoader.yieldToPanel();
    else if (!settings.music.enabled) this.audioLoader.restore();
  }

  private onGame(inGame: boolean): void {
    this.inGame = inGame;
    this.patch({ inGame });
    if (inGame) void rpc.cancelAmbientJobs().catch(() => undefined);
    this.applyGamePlan();
    void this.render();
  }

  private applyGamePlan(): void {
    const settings = this.settings();
    if (settings && this.snapshot.player.track) {
      const plan = planForGameState(this.inGame, settings.music.inGameMediaLevel);
      this.player.setScale(plan.volumeScale);
      if (!plan.playing) {
        this.savePosition();
        this.player.pause();
      } else if (!this.librarySession && !this.player.isPlaying && settings.music.enabled) this.player.resume();
    }
    this.syncGameVolume();
  }

  /** Re-applied on a timer too: a game opens its audio streams whenever it wants, and Pulse restores old volumes. */
  private syncGameVolume(): void {
    const settings = this.settings();
    if (!this.inGame) this.gameVolumeLowered = false;
    const target = settings ? gameVolumeTarget(this.inGame, this.player.isPlaying, settings.music.inGameGameLevel, this.gameVolumeLowered) : null;
    if (target === null || this.gameVolumeBusy) return;
    this.gameVolumeBusy = true;
    void rpc.setAmbientGameVolume(target)
      .then((result) => { if (result.supported) this.gameVolumeLowered = target < 100; })
      .catch(() => undefined)
      .finally(() => { this.gameVolumeBusy = false; });
  }

  private musicTracks(): Promise<Track[]> {
    const scan = this.snapshot.scan;
    return Promise.all((scan?.music ?? []).map(async (item) => ({
      id: item.id,
      title: item.name.replace(/\.[^.]+$/, ""),
      subtitle: "",
      art: "",
      url: (await this.resolve(item.id)) ?? "",
      live: false,
    }))).then((tracks) => tracks.filter((t) => t.url));
  }

  /** Music the user starts by choice, so the selected game's soundtrack stays out of its way. */
  playMyMusic(): Promise<void> {
    this.preferUserMusic();
    return this.startMusic();
  }

  async startMusic(): Promise<void> {
    if (this.librarySession) return;
    const settings = this.settings();
    if (!settings) return;
    this.player.setVolume(settings.music.volume);
    this.player.setVideoMode(settings.music.videoOn);
    if (settings.music.queue.length && await this.restoreSavedQueue(settings)) return;
    if (settings.music.source === "radio") {
      const station = this.currentStation
        ?? [...settings.radio.favorites, ...settings.collections.favorites].map(favoriteToStation).find((s) => s.id === settings.music.stationId)
        ?? (settings.music.stationId ? await rpc.resolveAmbientRadio(settings.music.stationId).catch(() => null) : null);
      if (station && !this.stopped && !this.librarySession) this.playStation(station, false);
      return;
    }
    const last = settings.music.lastTrack;
    const video = last?.id.startsWith("remote:")
      ? await this.libraryTrack({ ref: last.id, name: "", kind: settings.music.videoOn ? "video" : "audio", collection: "" }).catch(() => null)
      : last ? await this.localVideoTrack(last.id) : null;
    const tracks = video ? [video] : await this.musicTracks();
    if (this.stopped || this.librarySession) return;
    const start = last ? Math.max(0, tracks.findIndex((t) => t.id === last.id)) : 0;
    this.player.playQueue(tracks, start, last && tracks[start]?.id === last.id ? last.position : 0);
    this.render();
  }

  private async localVideoTrack(id: string): Promise<Track | null> {
    const scan = this.snapshot.scan;
    const item = Object.values(scan?.library ?? scan?.collections ?? {}).flat().find((m) => m.id === id && m.kind === "video");
    if (!item) return null;
    const url = await rpc.getAmbientMediaUrl(id).catch(() => null);
    return url ? { id, title: item.name.replace(/\.[^.]+$/, ""), subtitle: "", art: "", url, live: false, kind: "video" } : null;
  }

  async playMedia(id: string): Promise<void> {
    const track = await this.localVideoTrack(id);
    if (!track) return this.playSong(id);
    if (this.stopped) return;
    this.preferUserMusic();
    this.currentStation = null;
    this.player.setVideoMode(true);
    this.patch({ videoCollapsed: false });
    this.player.playQueue([track]);
    await this.updateSettings((s) => ({ ...s, music: { ...s.music, enabled: true, source: "music", videoOn: true, lastTrack: { id, position: 0 } } }));
  }

  async playSong(id: string): Promise<void> {
    const tracks = await this.musicTracks();
    const start = tracks.findIndex((t) => t.id === id);
    if (start < 0 || this.stopped) return;
    this.preferUserMusic();
    this.currentStation = null;
    this.player.playQueue(tracks, start);
    await this.updateSettings((s) => ({ ...s, music: { ...s.music, enabled: true, source: "music" } }));
  }

  playStation(station: Station, persist = true): void {
    if (persist) this.preferUserMusic();
    this.currentStation = station;
    this.player.playQueue([stationTrack(station)]);
    if (persist) void this.updateSettings((s) => ({ ...s, music: { ...s.music, enabled: true, source: "radio", stationId: station.id } }));
    void this.render();
  }

  pauseMusic(): void {
    if (this.librarySession) {
      this.captureLibraryPlayback();
      this.player.pause();
      return;
    }
    this.savePosition();
    this.player.pause();
    void this.updateSettings((s) => ({ ...s, music: { ...s.music, enabled: false } }));
    this.audioLoader.restore();
  }

  resumeMusic(): void {
    if (this.librarySession) {
      this.captureLibraryPlayback();
      this.player.resume();
      return;
    }
    this.preferUserMusic();
    if (this.snapshot.player.track) this.player.resume();
    else void this.startMusic();
    void this.updateSettings((s) => ({ ...s, music: { ...s.music, enabled: true } }));
    void this.render();
  }

  private scheduleQueueSave(player: PlayerSnapshot): void {
    if (this.librarySession || this.stopped || !this.snapshot.state) return;
    if (!this.queueLoaded && !player.track) return;
    this.queueLoaded = true;
    if (player.queue === this.lastQueue.queue && player.repeat === this.lastQueue.repeat && player.shuffle === this.lastQueue.shuffle) return;
    this.lastQueue = player;
    const queue = player.queue.map(({ track }) => toQueued(track));
    const signature = queueSignature(queue, player.repeat, player.shuffle);
    if (signature === this.savedQueue) return;
    if (this.queueSaveTimer !== null) clearTimeout(this.queueSaveTimer);
    this.queueSaveTimer = setTimeout(() => {
      this.queueSaveTimer = null;
      if (this.stopped || this.librarySession) return;
      this.savedQueue = signature;
      void this.updateSettings((s) => ({ ...s, music: { ...s.music, queue, repeat: player.repeat, shuffle: player.shuffle } }));
    }, QUEUE_SAVE_MS);
  }

  private async restoreSavedQueue(settings: AmbientSettings): Promise<boolean> {
    const tracks = (await Promise.all(settings.music.queue.map((entry) => this.queuedTrack(entry)))).filter((t): t is Track => t !== null);
    if (!tracks.length || this.stopped || this.librarySession) return false;
    const last = settings.music.lastTrack;
    const start = last ? Math.max(0, tracks.findIndex((t) => t.id === last.id)) : 0;
    const position = last && tracks[start]?.id === last.id && !tracks[start].live ? last.position : 0;
    this.player.restoreQueue(tracks, start, position, settings.music.repeat, settings.music.shuffle);
    this.render();
    return true;
  }

  private async queuedTrack(entry: QueuedTrack): Promise<Track | null> {
    const served = entry.url.startsWith("http://127.0.0.1:");
    const url = served ? await rpc.getAmbientMediaUrl(entry.id).catch(() => null) : entry.url;
    return url ? { id: entry.id, title: entry.title, subtitle: entry.subtitle, art: entry.art, url, live: entry.live, kind: entry.kind } : null;
  }

  /** Queues tracks; with nothing loaded the first one starts. */
  enqueue(tracks: Track[], where: "end" | "next" = "end"): void {
    if (!tracks.length || this.stopped) return;
    this.settleLibraryPreview(true);
    this.preferUserMusic();
    const starts = !this.player.getSnapshot().track;
    this.player.enqueue(tracks, where);
    if (starts) void this.updateSettings((s) => ({ ...s, music: { ...s.music, enabled: true } }));
  }

  /** Library items (songs, videos, links) as tracks, in the order given; missing ones are skipped. */
  async tracksFor(items: LibraryMediaItem[]): Promise<Track[]> {
    const tracks = await Promise.all(items.map((item) => this.libraryTrack(item).catch(() => null)));
    return tracks.filter((t): t is Track => t !== null);
  }

  /** Links sent from a phone or pasted: each one becomes a queue entry; pictures are left out. */
  enqueueLinks(urls: string[]): number {
    const tracks = urls.filter((url) => linkKind(url) !== "image").map(linkTrack);
    this.enqueue(tracks);
    return tracks.length;
  }

  /** Opens the page a phone on the same network uses to send links; texts are the page's own copy. */
  startShare(texts: Record<string, string>): Promise<rpc.ShareSession> {
    return rpc.startAmbientShare(texts).catch(() => ({ error: "unavailable" }));
  }

  /** Queues whatever the phone sent since the last call. */
  async pollShare(): Promise<{ added: number; active: boolean }> {
    const result = await rpc.takeAmbientShared().catch(() => ({ links: [] as string[], active: false }));
    return { added: result.links.length ? this.enqueueLinks(result.links) : 0, active: result.active };
  }

  stopShare(): void {
    void rpc.stopAmbientShare().catch(() => undefined);
  }

  enqueueStation(station: Station, where: "end" | "next" = "end"): void {
    this.enqueue([stationTrack(station)], where);
  }

  /** Library items added to the queue, at the end or right after what plays. */
  async enqueueItems(items: LibraryMediaItem[], where: "end" | "next" = "end"): Promise<number> {
    const tracks = await this.tracksFor(items);
    this.enqueue(tracks, where);
    return tracks.length;
  }

  /** Plays a whole folder (or My music) from its first song. */
  async playCollection(collection: string, where: "now" | "end" = "now"): Promise<boolean> {
    const scan = this.snapshot.scan;
    const media = scan?.library?.[collection] ?? (collection === "known.music" ? scan?.music : scan?.collections[collection]) ?? [];
    const tracks = await this.tracksFor(media.filter((m) => m.kind !== "image").map((m) => ({ ref: m.id, name: m.name.replace(/\.[^.]+$/, ""), kind: m.kind, collection })));
    if (!tracks.length || this.stopped) return false;
    if (where === "end") this.enqueue(tracks);
    else this.playTracks(tracks);
    return true;
  }

  playTracks(tracks: Track[], start = 0): void {
    if (!tracks.length || this.stopped) return;
    this.settleLibraryPreview(false);
    this.preferUserMusic();
    this.currentStation = null;
    this.player.playQueue(tracks, start, 0, tracks[start]?.kind === "video" || this.player.getSnapshot().video);
    void this.updateSettings((s) => ({ ...s, music: { ...s.music, enabled: true, source: "music" } }));
  }

  playQueueEntry(key: string): void { this.player.playEntry(key); }
  removeQueueEntry(key: string): void { this.player.removeEntry(key); }
  moveQueueEntry(key: string, to: number): void { this.player.moveEntry(key, to); }
  clearQueue(): void { this.player.clearQueue(); }
  setRepeat(repeat: RepeatMode): void { this.player.setRepeat(repeat); }
  setShuffle(on: boolean): void { this.player.setShuffle(on); }

  /**
   * A deliberate choice in the library ends its preview: queueing builds on what played before the
   * preview, playing replaces it. Either way closing the library no longer rolls it back.
   */
  private settleLibraryPreview(keepPrevious: boolean): void {
    const session = this.librarySession;
    if (!session?.modified) return;
    if (keepPrevious) {
      this.currentStation = session.station;
      this.player.restore(session.checkpoint);
    }
    session.modified = false;
  }

  /** What the user puts on wins over the selected game's soundtrack until another game is selected. */
  private preferUserMusic(): void {
    this.themeSilencedFor = this.lastSelectedAppId;
    this.themePausedMusic = false;
  }

  canShowVideo(): boolean {
    return this.player.canShowVideo();
  }

  setVideo(on: boolean): void {
    this.captureLibraryPlayback();
    if (!on) this.setVideoFullscreen(false);
    this.player.setVideoMode(on);
    this.patch({ videoCollapsed: false });
    if (!this.librarySession && this.settings()?.music.videoOn !== on) void this.updateSettings((s) => ({ ...s, music: { ...s.music, videoOn: on } }));
  }

  private openPages = 0;

  /** The page calls this while mounted; the returned function marks it closed again. */
  markPageOpen(): () => void {
    this.openPages += 1;
    this.patch({ pageOpen: true });
    return () => {
      this.openPages = Math.max(0, this.openPages - 1);
      this.patch({ pageOpen: this.openPages > 0 });
    };
  }

  startOverlayControl(): void {
    try {
      Navigation.CloseSideMenus();
    } catch {
      /* no side menu open */
    }
    this.patch({ overlayControl: true });
  }

  stopOverlayControl(then?: "main-menu" | "quick-access"): void {
    if (this.snapshot.videoFullscreen) void rpc.recordAmbientEvent("video_fullscreen", "exit").catch(() => undefined);
    this.controlBeforeFullscreen = false;
    this.patch({ overlayControl: false, videoFullscreen: false });
    try {
      if (then === "main-menu") Navigation.OpenMainMenu();
      else if (then === "quick-access") Navigation.OpenQuickAccessMenu();
    } catch {
      /* Steam handles its own button next time */
    }
  }

  /** Shows or folds the video; the first time it moves playback into the video window. */
  toggleVideo(): void {
    this.setVideoFullscreen(false);
    if (!this.snapshot.player.video) this.setVideo(true);
    else this.patch({ videoCollapsed: !this.snapshot.videoCollapsed });
  }

  private controlBeforeFullscreen = false;

  setVideoFullscreen(on: boolean): void {
    if (on === this.snapshot.videoFullscreen) return;
    if (on) {
      if (!this.snapshot.player.video || this.snapshot.videoCollapsed) return;
      this.controlBeforeFullscreen = this.snapshot.overlayControl;
      if (this.librarySession) this.patch({ overlayControl: true });
      else this.startOverlayControl();
      this.patch({ videoFullscreen: true });
    } else {
      this.patch({ videoFullscreen: false, overlayControl: this.controlBeforeFullscreen });
      this.controlBeforeFullscreen = false;
    }
    void rpc.recordAmbientEvent("video_fullscreen", on ? "enter" : "exit").catch(() => undefined);
  }

  setVideoBounds(bounds: VideoBounds): void {
    this.player.setVideoBounds(bounds);
  }

  setVideoVisible(visible: boolean): void {
    this.player.setVideoVisible(visible);
  }

  seekFraction(fraction: number): void {
    this.captureLibraryPlayback();
    const duration = this.snapshot.player.duration;
    if (duration) this.player.seekTo(fraction * duration);
  }

  seekBy(seconds: number): void {
    this.captureLibraryPlayback();
    this.player.seekTo(this.snapshot.player.position + seconds);
  }

  nextTrack(): void {
    this.captureLibraryPlayback();
    if (!this.librarySession) this.preferUserMusic();
    this.player.next();
  }

  previousTrack(): void {
    this.captureLibraryPlayback();
    if (!this.librarySession) this.preferUserMusic();
    this.player.previous();
  }

  setVolume(volume: number): void {
    this.captureLibraryPlayback();
    this.player.setVolume(volume);
    if (this.librarySession) {
      return;
    }
    void this.updateSettings((s) => ({ ...s, music: { ...s.music, volume } }));
  }

  private savePosition(): void {
    if (this.snapshot.libraryOpen) return;
    const track = this.snapshot.player.track;
    const settings = this.settings();
    if (!track || !settings) return;
    const position = track.live ? 0 : this.player.position();
    if (settings.music.lastTrack?.id === track.id && Math.abs(settings.music.lastTrack.position - position) < 5) return;
    void this.updateSettings((s) => ({ ...s, music: { ...s.music, lastTrack: { id: track.id, position } } }));
  }

  async loadSuggestedStations(): Promise<void> {
    if (this.snapshot.suggestedStations.length) return;
    const stations = await rpc.getAmbientSuggestedStations().catch(() => [] as Station[]);
    this.patch({ suggestedStations: stations });
  }

  private catalog: Promise<RadioCatalog> | null = null;

  radioCatalog(): Promise<RadioCatalog> {
    this.catalog ??= rpc.getAmbientRadioCatalog().catch(() => {
      this.catalog = null;
      return { countries: [], tags: [] };
    });
    return this.catalog;
  }

  discoverRadio(filters: RadioFilters): Promise<Station[]> {
    return rpc.discoverAmbientRadio(filters).catch(() => [] as Station[]);
  }

  searchRadio(query: string): Promise<Station[]> {
    return rpc.searchAmbientRadio(query, "", "").catch(() => [] as Station[]);
  }


  async updateSettings(change: (settings: AmbientSettings) => AmbientSettings): Promise<void> {
    const state = this.snapshot.state;
    if (!state) return;
    const next = change(state.settings);
    this.patch({ state: { ...state, settings: next } });
    const levels = (m: AmbientSettings["music"]) => `${m.inGameMediaLevel}/${m.inGameGameLevel}`;
    if (this.inGame && levels(next.music) !== levels(state.settings.music)) this.applyGamePlan();
    const sequence = ++this.saveSequence;
    const save = this.saveChain.then(() => rpc.saveAmbientSettings(next));
    this.saveChain = save.then(() => undefined, () => undefined);
    try {
      const saved = await save;
      const latest = this.snapshot.state;
      if (latest && sequence === this.saveSequence) this.patch({ state: { ...latest, settings: saved } });
    } catch {
      this.patch({ error: "save_failed" });
    }
    if (next.background.order !== state.settings.background.order) this.rotation = createRotation(next.background.order);
    if (next.background.collections.join() !== state.settings.background.collections.join() ||
      (next.background.selectedRefs ?? []).join() !== (state.settings.background.selectedRefs ?? []).join()) {
      await this.rebuildItems();
      this.advanceRotation();
    } else void this.render();
  }

  assignCurrentToSelectedGame(): Promise<void> {
    const game = this.snapshot.selectedGame;
    const ref = this.snapshot.current?.ref;
    if (!game || !ref) return Promise.resolve();
    return this.updateSettings((s) => ({ ...s, background: { ...s.background, perGame: { ...s.background.perGame, [game.appid]: ref } } }));
  }

  clearSelectedGame(): Promise<void> {
    const game = this.snapshot.selectedGame;
    return game ? this.clearGameBackground(game.appid) : Promise.resolve();
  }

  clearGameBackground(appid: string): Promise<void> {
    return this.updateSettings((s) => {
      const perGame = { ...s.background.perGame };
      delete perGame[appid];
      return { ...s, background: { ...s.background, perGame } };
    });
  }

  showMineOver(ids: readonly string[]): Promise<void> {
    return this.updateSettings((s) => ({ ...s, claims: { ...s.claims, ...Object.fromEntries(ids.map((id) => [id, "panel" as const])) } }));
  }

  choose(id: string, owner: ClaimOwner): Promise<void> {
    return this.updateSettings((s) => ({ ...s, claims: { ...s.claims, [id]: owner } }));
  }

  toggleCollection(id: string, enabled: boolean): Promise<void> {
    return this.updateSettings((s) => {
      const collections = s.background.collections.filter((c) => c !== id);
      return { ...s, background: { ...s.background, selectedRefs: [], collections: enabled ? [...collections, id] : collections } };
    });
  }

  /** Folders change what is on disk, so they rescan; favorites and removals only re-read the state. */
  private async applyServerSettings(result: Promise<AmbientSettings | null>, rescan = false): Promise<boolean> {
    const settings = await result.catch(() => null);
    if (!settings) return false;
    if (rescan) {
      await this.reload();
      return true;
    }
    const state = await rpc.getAmbientState().catch(() => null);
    if (!state || this.stopped) return false;
    this.patch({ state });
    await this.rebuildItems();
    void this.render();
    return true;
  }

  addFolder(path: string, scope: "background" | "music" | "library"): Promise<boolean> {
    return this.applyServerSettings(rpc.addAmbientFolder(path, scope), true);
  }

  addFavorite(scope: "background" | "radio", url: string, name: string, art = "", subtitle = ""): Promise<boolean> {
    return this.applyServerSettings(rpc.addAmbientFavorite(scope, url, name, art, subtitle));
  }

  addPlaylist(url: string, name: string): Promise<boolean> {
    return this.applyServerSettings(rpc.addAmbientPlaylist(url, name));
  }

  removePlaylist(id: string): Promise<boolean> {
    this.playlists.delete(id);
    return this.applyServerSettings(rpc.removeAmbientPlaylist(id));
  }

  private playlists = new Map<string, Promise<PlaylistContents>>();

  /** Channels of a saved list; one request per list while Panel runs, failures are retried. */
  playlist(id: string): Promise<PlaylistContents> {
    const cached = this.playlists.get(id);
    if (cached) return cached;
    const pending = rpc.getAmbientPlaylist(id)
      .then((contents) => contents ?? { id, channels: [], error: "unreachable" })
      .catch(() => ({ id, channels: [], error: "unreachable" }))
      .then((contents) => {
        if (contents.error) this.playlists.delete(id);
        return contents;
      });
    this.playlists.set(id, pending);
    return pending;
  }

  /** Only streams (radio, YouTube, Twitch, TV) are kept as favorites; own songs are not. */
  canFavoriteTrack(): boolean {
    const track = this.snapshot.player.track;
    return !!track && trackSource(track) === "radio";
  }

  isFavoriteTrack(): boolean {
    const track = this.snapshot.player.track;
    return !!track && !!this.settings()?.radio.favorites.some((f) => f.url === track.url);
  }

  toggleFavoriteTrack(): void {
    const track = this.snapshot.player.track;
    if (!track || !this.canFavoriteTrack()) return;
    void this.toggleFavoriteStation({ id: track.id, name: track.title, url: track.url, favicon: track.art, country: track.subtitle, countryCode: "", tags: [], codec: "", bitrate: 0 });
  }

  isFavoriteStation(station: Station): boolean {
    return !!this.settings()?.radio.favorites.some((f) => f.url === station.url);
  }

  toggleFavoriteStation(station: Station): Promise<boolean> {
    const existing = this.settings()?.radio.favorites.find((f) => f.url === station.url);
    if (existing) return this.removeItem("radio", existing.id);
    return this.addFavorite("radio", station.url, station.name, station.favicon, stationSubtitle(station));
  }

  async removeItem(scope: "background" | "radio" | "music" | "library", id: string): Promise<boolean> {
    const pinned = this.settings()?.background.pinned;
    const removedPinnedSource = !!pinned && this.snapshot.items.some((item) => item.ref === pinned && item.collection === id);
    const settings = await rpc.removeAmbientItem(scope, id).catch(() => null);
    if (!settings) return false;
    this.clearMediaCache();
    if (!await this.applyServerSettings(Promise.resolve(settings), scope !== "radio" || id.startsWith("folder."))) return false;
    if (removedPinnedSource && this.settings()?.background.pinned === pinned && !this.snapshot.items.some((item) => item.ref === pinned)) {
      await this.updateSettings((s) => ({ ...s, background: { ...s.background, pinned: "" } }));
      this.advanceRotation();
      if (this.snapshot.error === "save_failed") return false;
    }
    return true;
  }

  restoreSuggested(scope: "background" | "radio", itemId = ""): Promise<boolean> {
    return this.applyServerSettings(rpc.restoreAmbientSuggested(scope, itemId));
  }
}

export function channelToStation(channel: Channel): Station {
  return { id: channel.id, name: channel.name, url: channel.url, favicon: channel.logo, country: channel.group, countryCode: "", tags: [], codec: "", bitrate: 0 };
}

function liveStream(url: string): boolean {
  if (parseYouTube(url)) return false;
  const embed = parseEmbedStream(url);
  return embed ? isLiveEmbed(embed) : true;
}

function toQueued(track: Track): QueuedTrack {
  return { id: track.id, url: track.url, title: track.title, subtitle: track.subtitle, art: track.art, kind: track.kind ?? "audio", live: track.live };
}

function queueSignature(queue: readonly QueuedTrack[], repeat: RepeatMode, shuffle: boolean): string {
  return JSON.stringify([repeat, shuffle, queue.map((q) => q.id)]);
}

function stationTrack(station: Station): Track {
  return { id: station.id, title: station.name, subtitle: stationSubtitle(station), art: station.favicon, url: station.url, live: liveStream(station.url), countryCode: station.countryCode || undefined };
}

function linkTrack(url: string): Track {
  const file = linkKind(url);
  return { id: `remote:${url}`, title: linkName(url), subtitle: "", art: "", url, live: file ? false : liveStream(url), kind: file === "video" ? "video" : "audio" };
}
