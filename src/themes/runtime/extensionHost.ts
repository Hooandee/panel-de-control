import type { ThemeGroupsAccess } from "../../groups/groupsClient";
import { artworkStoreOf, type ThemeArtworkAccess, type ThemeArtworkStore } from "../artwork";
import type { CssLoaderPatch, CssLoaderSnapshot, CssLoaderTheme } from "../cssLoaderTypes";
import type {
  ThemeExtensionClient,
  ThemeExtensionDescriptor,
  ThemeExtensionPayload,
} from "../themeExtensionClient";
import type { ThemeExtensionLibraryAccess } from "./libraryAccess";
import type { ThemeExtensionNavigationAccess } from "./navigationAccess";
import type { ThemeExtensionStorageAccess, ThemeStorageProvider } from "./themeStorage";
import type { ThemeExtensionGamesAccess } from "./gamesAccess";
import type { ThemeActionsAccess, ThemeActionsProvider } from "./themeActions";
import { SECTION_ON, sectionKeyOf } from "../sectionOwnership";
import { ThemeOptionsChannel, type ThemeOptionsAccess, type ThemeOptionsWriter } from "./themeOptions";
import { keptThemeImageRefs, validThemeImageRef } from "../../ambient/steam/themeImages";

export type { ThemeOptionsAccess, ThemeOptionsWriter } from "./themeOptions";

export interface ThemeExtensionHostDescriptor {
  abiVersion: 1;
}

export interface AmbientBackgroundState {
  owner: "panel" | "theme";
  media: { url: string; kind: "image" | "video" } | null;
  motion: "play" | "pause" | "freeze";
  /**
   * Whether Ambiente's music (own files, queue or radio) is audibly playing now. A gap between tracks is
   * reported only once it lasts; absent on older Panels, which a theme reads as not playing.
   */
  music?: { playing: boolean };
}

export interface AmbientClaimOptions {
  name: string;
  surfaces: readonly ("home" | "library")[];
  mode: "yield" | "host";
}

/** What a theme runtime sees: an optional channel, present only when Panel offers Ambiente. */
export interface ThemeExtensionAmbientAccess {
  claim(options: AmbientClaimOptions): () => void;
  getState(): AmbientBackgroundState;
  subscribe(listener: (state: AmbientBackgroundState) => void): () => void;
  /**
   * The picture or video element Panel is painting now (owner "panel"), readable by canvas and WebGL, so
   * a theme can mirror the real background. Null when Panel paints nothing or a stream it cannot share.
   * The element stays Panel's: draw from it, never move, restyle or keep it.
   */
  frame(): HTMLImageElement | HTMLVideoElement | null;
  /**
   * The game selected on a Home the theme draws itself, so Ambiente can play its soundtrack and trailer.
   * `null` when nothing is selected. Dropped on unmount; absent on older Panels.
   */
  select?(appid: string | number | null): void;
  /**
   * Opens Ambiente's photo explorer over Big Picture to choose one picture. Settles with a stable `ref` (opaque,
   * at most 512 characters, the same across reboots) and a loopback `url` Big Picture can load; images loaded
   * with `crossOrigin="anonymous"` can be read by canvas and WebGL. Null when the user backs out, when another
   * picker is open, or when the theme unmounts first. Absent on older Panels and on Windows. On the Deck it is
   * present even while Ambiente cannot serve pictures (for example while its runtime is stopped): it then
   * settles null, as when the user backs out.
   * `maxSide`: as in `imageUrl`.
   */
  pickImage?(options?: { title?: string; maxSide?: number }): Promise<{ ref: string; url: string } | null>;
  /**
   * The current URL for a ref `pickImage` returned, also after a reboot. Null for an unknown ref, a ref this theme
   * does not keep (another theme's picture), a file that is gone, an absurd or unreadable picture, or until Panel
   * has loaded its references shortly after it starts.
   * Synchronous and cheap.
   * `maxSide`: the long side, in device pixels, of the screen Big Picture draws on. Panel snaps it up to 1280,
   * 1920 or 2560 (absent or invalid: 2560) and serves a copy no larger, EXIF orientation applied, or the
   * original when it already fits. Each size has its own URL; a copy is made on the first request for it.
   */
  imageUrl?(ref: string, maxSide?: number): string | null;
  /** Called when `imageUrl` answers may have changed (references loaded, a file went missing or came back). */
  subscribeImages?(listener: () => void): () => void;
  /**
   * The complete list of refs this theme still shows somewhere. Every picture of this theme not listed is
   * forgotten: its ref stops resolving and, unless another theme still keeps it, its cached copies are deleted
   * (never the user's files). So list every ref in use, including one `pickImage` returned since the last call.
   * Calls and picks reach Panel in the order made. Cheap to call on every layout save: an unchanged list does
   * nothing. Ignored unless it is an array of at most 512 refs.
   */
  keepImages?(refs: readonly string[]): void;
}

/** What the orchestrator provides; claims are keyed by the theme that makes them. */
export interface AmbientChannelProvider {
  claim(themeId: string, options: AmbientClaimOptions): () => void;
  getState(): AmbientBackgroundState;
  subscribe(listener: (state: AmbientBackgroundState) => void): () => void;
  frame?(): HTMLImageElement | HTMLVideoElement | null;
  select?(themeId: string, appid: string | null): () => void;
  /** `owner` is the mounted theme's catalog id: pictures are registered and forgotten per theme. */
  pickImage?(owner: string, options: { title?: string; maxSide?: number }, signal: AbortSignal): Promise<{ ref: string; url: string } | null>;
  imageUrl?(owner: string, ref: string, maxSide?: number): string | null;
  subscribeImages?(listener: () => void): () => void;
  keepImages?(owner: string, refs: readonly string[]): void;
}

const MAX_IMAGE_TITLE = 80;

function screenSide(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : undefined;
}

export interface ThemeExtensionQamAccess {
  getDocument(): Document | null;
  subscribe(listener: (doc: Document) => void): () => void;
}

export interface ThemeExtensionMountContextV1 {
  artwork?: Readonly<ThemeArtworkAccess>;
  theme: Readonly<CssLoaderTheme>;
  document: Document;
  host: Readonly<ThemeExtensionHostDescriptor>;
  qam?: never;
  ambient?: Readonly<ThemeExtensionAmbientAccess>;
  navigation?: Readonly<Pick<ThemeExtensionNavigationAccess, "focus">>;
  /** Durable storage scoped to this theme's catalog id; absent on a Panel that does not offer it. */
  storage?: Readonly<ThemeExtensionStorageAccess>;
  /** Groups shared by every theme (hand-picked and rule based); absent on a Panel that does not offer them. */
  groups?: Readonly<ThemeGroupsAccess>;
  /** Game controls Steam lacks (force close); absent where Panel cannot offer them, e.g. Windows. */
  games?: Readonly<ThemeExtensionGamesAccess>;
  /** The theme's own `actions` (panel-theme.json), pressed in its Panel settings; absent where Panel does not offer them. */
  actions?: Readonly<ThemeActionsAccess>;
  /** This theme's own CSS Loader options, live and writable; absent where Panel cannot write them (Windows). */
  options?: Readonly<ThemeOptionsAccess>;
}

export interface ThemeExtensionMountContextV2 {
  artwork?: Readonly<ThemeArtworkAccess>;
  theme: Readonly<CssLoaderTheme>;
  document: Document;
  host: Readonly<ThemeExtensionHostDescriptor>;
  qam: Readonly<ThemeExtensionQamAccess>;
  library?: Readonly<ThemeExtensionLibraryAccess>;
  navigation?: Readonly<ThemeExtensionNavigationAccess>;
  ambient?: Readonly<ThemeExtensionAmbientAccess>;
  /** Durable storage scoped to this theme's catalog id; absent on a Panel that does not offer it. */
  storage?: Readonly<ThemeExtensionStorageAccess>;
  /** Groups shared by every theme (hand-picked and rule based); absent on a Panel that does not offer them. */
  groups?: Readonly<ThemeGroupsAccess>;
  /** Game controls Steam lacks (force close); absent where Panel cannot offer them, e.g. Windows. */
  games?: Readonly<ThemeExtensionGamesAccess>;
  /** The theme's own `actions` (panel-theme.json), pressed in its Panel settings; absent where Panel does not offer them. */
  actions?: Readonly<ThemeActionsAccess>;
  /** This theme's own CSS Loader options, live and writable; absent where Panel cannot write them (Windows). */
  options?: Readonly<ThemeOptionsAccess>;
}

export type ThemeExtensionMountContext =
  | ThemeExtensionMountContextV1
  | ThemeExtensionMountContextV2;

export type ThemeExtensionSurface = "home" | "keyboard";

export interface ThemeExtensionExportV1 {
  abiVersion: 1;
  surface?: "keyboard";
  mount(context: ThemeExtensionMountContextV1): () => void;
}

export interface ThemeExtensionExportV2 {
  abiVersion: 2;
  surface?: "keyboard";
  mount(context: ThemeExtensionMountContextV2): () => void;
}

export type ThemeExtensionExport = ThemeExtensionExportV1 | ThemeExtensionExportV2;

type ExtensionEvaluator = (source: string) => ThemeExtensionExport;
type ExtensionLogCode =
  | "extension_list_failed"
  | "extension_load_failed"
  | "extension_payload_mismatch"
  | "extension_evaluation_failed"
  | "extension_mount_failed"
  | "extension_dispose_failed"
  | "extension_release_failed"
  | "options_write_failed"
  | "options_listener_failed"
  | "keyboard_theme_retire_failed";

interface ThemeExtensionRuntimeHostOptions {
  /** Cover stores by name; a theme only sees the store its catalog id is allowed (`artworkStoreOf`). */
  artwork?: Readonly<Partial<Record<ThemeArtworkStore, ThemeArtworkAccess>>>;
  options?: ThemeOptionsWriter;
  client: ThemeExtensionClient;
  doc: Document;
  qam?: ThemeExtensionQamAccess;
  library?: ThemeExtensionLibraryAccess;
  navigation?: ThemeExtensionNavigationAccess;
  ambient?: AmbientChannelProvider;
  storage?: ThemeStorageProvider;
  games?: Readonly<ThemeExtensionGamesAccess>;
  groups?: Readonly<ThemeGroupsAccess>;
  actions?: ThemeActionsProvider;
  /** Turns a theme off in CSS Loader; absent where Panel cannot write CSS Loader state (Windows). */
  retireTheme?(cssLoaderName: string, keep: string): Promise<boolean>;
  evaluate?: ExtensionEvaluator;
  log?(code: ExtensionLogCode): void;
}

interface RuntimeSelection {
  descriptor: ThemeExtensionDescriptor;
  theme: CssLoaderTheme;
  key: string;
  fingerprint: string;
}

interface ActiveRuntime {
  stop: () => void;
  key: string;
  structure: string;
  /** True while the runtime holds an options subscription: it follows value changes itself instead of being remounted. */
  followsOptions: () => boolean;
}

class ThemeExtensionPayloadMismatchError extends Error {}

const HOST_DESCRIPTOR: Readonly<ThemeExtensionHostDescriptor> = Object.freeze({ abiVersion: 1 });

export function ambientThemeId(themeName: string): string {
  return themeName.trim().toLowerCase().replace(/[^a-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 64) || "theme";
}

const AMBIENT_SURFACES = new Set(["home", "library"]);

/** Scopes the channel to one mount so every claim a runtime forgets is released when it unmounts. */
function scopedAmbientAccess(provider: AmbientChannelProvider, themeId: string, owner: string): { access: Readonly<ThemeExtensionAmbientAccess>; release(): void } {
  const releases = new Set<() => void>();
  const listeners = new Set<() => void>();
  let releaseSelection: (() => void) | null = null;
  const access: ThemeExtensionAmbientAccess = {
    claim(options) {
      const surfaces = Array.isArray(options?.surfaces) ? options.surfaces.filter((s) => AMBIENT_SURFACES.has(s)) : [];
      const mode = options?.mode === "host" ? "host" : "yield";
      const name = typeof options?.name === "string" && options.name.trim() ? options.name.trim().slice(0, 60) : themeId;
      const releaseClaim = provider.claim(themeId, { name, surfaces, mode });
      let released = false;
      const release = () => {
        if (released) return;
        released = true;
        releases.delete(release);
        releaseClaim();
      };
      releases.add(release);
      return release;
    },
    getState: () => provider.getState(),
    frame: () => provider.frame?.() ?? null,
    ...(provider.select ? {
      select(appid: string | number | null) {
        if (releaseSelection) releases.delete(releaseSelection);
        releaseSelection = provider.select!(themeId, appid == null ? null : String(appid));
        releases.add(releaseSelection);
      },
    } : {}),
    subscribe: (listener) => track(provider.subscribe(listener)),
    ...(provider.pickImage ? {
      async pickImage(options?: { title?: string; maxSide?: number }) {
        const title = typeof options?.title === "string" ? options.title.trim().slice(0, MAX_IMAGE_TITLE) : "";
        const maxSide = screenSide(options?.maxSide);
        const controller = new AbortController();
        const abort = () => controller.abort();
        releases.add(abort);
        try {
          const pick = await provider.pickImage!(owner, { ...(title ? { title } : {}), ...(maxSide ? { maxSide } : {}) }, controller.signal);
          return pick && typeof pick.ref === "string" && typeof pick.url === "string" && !controller.signal.aborted ? { ref: pick.ref, url: pick.url } : null;
        } catch {
          return null;
        } finally {
          releases.delete(abort);
        }
      },
    } : {}),
    ...(provider.imageUrl ? {
      imageUrl(ref: string, maxSide?: number) {
        if (!validThemeImageRef(ref)) return null;
        try { return provider.imageUrl!(owner, ref, screenSide(maxSide)); } catch { return null; }
      },
    } : {}),
    ...(provider.subscribeImages ? {
      subscribeImages: (listener: () => void) => track(provider.subscribeImages!(listener)),
    } : {}),
    ...(provider.keepImages ? {
      keepImages(refs: readonly string[]) {
        const kept = keptThemeImageRefs(refs);
        if (!kept) return;
        try { provider.keepImages!(owner, kept); } catch { /* the theme's layout save must not fail on Panel */ }
      },
    } : {}),
  };
  function track(off: () => void): () => void {
    let active = true;
    const unsubscribe = () => {
      if (!active) return;
      active = false;
      listeners.delete(unsubscribe);
      off();
    };
    listeners.add(unsubscribe);
    return unsubscribe;
  }
  return {
    access: Object.freeze(access),
    release() {
      for (const release of [...releases]) release();
      for (const unsubscribe of [...listeners]) unsubscribe();
    },
  };
}

// Steam's global button handlers consume input for the whole UI; a theme that throws in mount or in
// its disposer must not leave a capture or a QAM subscription behind.
class MountScope {
  private readonly releases = new Set<() => void>();
  private closed = false;

  constructor(private readonly log: (code: ExtensionLogCode) => void) {}

  track(release: () => void): () => void {
    if (typeof release !== "function") return () => {};
    if (this.closed) {
      try {
        release();
      } catch {
        this.log("extension_release_failed");
      }
      return () => {};
    }
    let active = true;
    const once = () => {
      if (!active) return;
      active = false;
      this.releases.delete(once);
      release();
    };
    this.releases.add(once);
    return once;
  }

  releaseAll(): void {
    this.closed = true;
    for (const release of [...this.releases].reverse()) {
      try {
        release();
      } catch {
        this.log("extension_release_failed");
      }
    }
  }
}

function exactKeys(value: object, expected: readonly string[]): boolean {
  const keys = Object.keys(value);
  return keys.length === expected.length && expected.every((key) => keys.includes(key));
}

export function evaluateThemeExtensionBundle(source: string): ThemeExtensionExport {
  const localModule: { exports: unknown } = { exports: {} };
  const execute = new Function("module", "exports", `"use strict";\n${source}`);
  execute(localModule, localModule.exports);
  const extension = localModule.exports;
  if (
    typeof extension !== "object"
    || extension === null
    || Array.isArray(extension)
    || !Object.isFrozen(extension)
    || !(exactKeys(extension, ["abiVersion", "mount"])
      || (exactKeys(extension, ["abiVersion", "mount", "surface"]) && Reflect.get(extension, "surface") === "keyboard"))
    || (Reflect.get(extension, "abiVersion") !== 1 && Reflect.get(extension, "abiVersion") !== 2)
    || typeof Reflect.get(extension, "mount") !== "function"
  ) throw new Error("Theme extension export is invalid");
  return extension as ThemeExtensionExport;
}

function freezePatch(patch: CssLoaderPatch): Readonly<CssLoaderPatch> {
  return Object.freeze({ ...patch, options: Object.freeze([...patch.options]) });
}

// A game the theme froze thaws when the theme goes, not only when the backend's deadline passes.
function scopedGames(games: Readonly<ThemeExtensionGamesAccess>, scope: MountScope): Readonly<ThemeExtensionGamesAccess> {
  let release: (() => void) | null = null;
  const forceClose = games.forceClose;
  return Object.freeze({
    ...(forceClose ? { forceClose: (appid: number | string) => forceClose.call(games, appid) } : {}),
    pause: (ms: number) => {
      release ??= scope.track(() => { void games.resume(); });
      return games.pause(ms);
    },
    resume: () => games.resume(),
  });
}

/** The shared groups, with the theme's subscriptions dropped when it unmounts. */
function scopedGroups(groups: Readonly<ThemeGroupsAccess>, scope: MountScope): Readonly<ThemeGroupsAccess> {
  const access: ThemeGroupsAccess = {
    list: () => groups.list(),
    subscribe: (listener) => scope.track(groups.subscribe(listener)),
    save: (group) => groups.save(group),
    remove: (id) => groups.remove(id),
    preview: (rules, extra) => groups.preview(rules, extra),
    catalog: (language) => groups.catalog(language),
    importSources: () => groups.importSources(),
    import: (ids) => groups.import(ids),
    migrate: (legacy) => groups.migrate(legacy),
    status: () => groups.status(),
  };
  return Object.freeze(access);
}

/** Only this theme's actions, with its listeners dropped when it unmounts. */
function scopedActions(actions: ThemeActionsProvider, catalogId: string, scope: MountScope): Readonly<ThemeActionsAccess> {
  return Object.freeze({
    subscribe: (listener: (id: string) => void) => scope.track(actions.subscribe(catalogId, listener)),
  });
}

function freezeTheme(theme: CssLoaderTheme): Readonly<CssLoaderTheme> {
  return Object.freeze({ ...theme, patches: Object.freeze(theme.patches.map(freezePatch)) });
}

// What still forces a remount of a runtime that follows its own options: a new version or a section changing hands.
function runtimeStructure(theme: CssLoaderTheme): string {
  const sections = theme.patches
    .filter((patch) => sectionKeyOf(patch.name) !== null)
    .map((patch) => [patch.name, patch.value] as const)
    .sort(([left], [right]) => left.localeCompare(right, "en"));
  return JSON.stringify({ version: theme.version, sections });
}

function scopedArtwork(artwork: ThemeArtworkAccess, scope: MountScope): Readonly<ThemeArtworkAccess> {
  scope.track(artwork.attach?.() ?? (() => {}));
  return Object.freeze({
    get: artwork.get,
    edit: artwork.edit,
    ...(artwork.editor ? { editor: Object.freeze({ ...artwork.editor }) } : {}),
    subscribe: (listener: () => void) => scope.track(artwork.subscribe(listener)),
  });
}

function themeFingerprint(theme: CssLoaderTheme): string {
  const patches = theme.patches
    .map((patch) => [patch.name, patch.value] as const)
    .sort(([left], [right]) => left.localeCompare(right, "en"));
  return JSON.stringify({ version: theme.version, patches });
}

// A theme without its own QAM section styles the QAM from its menus section (Gallery).
function claimedSections(theme: CssLoaderTheme): string[] | null {
  const sections = theme.patches.filter((patch) => sectionKeyOf(patch.name) !== null);
  if (sections.length === 0) return null;
  const claimed = sections.filter((patch) => patch.value === SECTION_ON).map((patch) => sectionKeyOf(patch.name)!);
  const hasQamSection = sections.some((patch) => sectionKeyOf(patch.name) === "qam");
  return claimed.includes("menu") && !hasQamSection ? [...claimed, "qam"] : claimed;
}

function homeRuntimes(group: readonly RuntimeSelection[]): readonly RuntimeSelection[] {
  if (group.length === 1) return group;
  const claims = group.map((selection) => claimedSections(selection.theme));
  if (claims.some((claim) => claim === null)) return [];
  const counts = new Map<string, number>();
  for (const key of claims.flat() as string[]) counts.set(key, (counts.get(key) ?? 0) + 1);
  if ([...counts.values()].every((count) => count === 1)) return group;
  const owners = group.filter((_, index) => claims[index]!.includes("home"));
  return owners.length === 1 ? owners : [];
}

function surfaceOf(extension: ThemeExtensionExport): ThemeExtensionSurface {
  return extension.surface === "keyboard" ? "keyboard" : "home";
}

function descriptorKey(descriptor: ThemeExtensionDescriptor): string {
  return `${descriptor.catalogId}\0${descriptor.version}\0${descriptor.sha256}`;
}

function payloadMatches(
  payload: ThemeExtensionPayload,
  descriptor: ThemeExtensionDescriptor,
): boolean {
  return payload.catalogId === descriptor.catalogId
    && payload.cssLoaderName === descriptor.cssLoaderName
    && payload.version === descriptor.version
    && payload.abiVersion === descriptor.abiVersion
    && payload.sha256 === descriptor.sha256;
}

export class ThemeExtensionRuntimeHost {
  private readonly artwork: Readonly<Partial<Record<ThemeArtworkStore, ThemeArtworkAccess>>> | undefined;
  private readonly options: ThemeOptionsChannel | undefined;
  private readonly client: ThemeExtensionClient;
  private readonly doc: Document;
  private readonly qam: Readonly<ThemeExtensionQamAccess> | undefined;
  private readonly library: Readonly<ThemeExtensionLibraryAccess> | undefined;
  private readonly navigation: Readonly<ThemeExtensionNavigationAccess> | undefined;
  private readonly evaluate: ExtensionEvaluator;
  private readonly log: (code: ExtensionLogCode) => void;
  private descriptors: readonly ThemeExtensionDescriptor[] | null = null;
  private descriptorRequest: Promise<void> | null = null;
  private snapshot: CssLoaderSnapshot = { status: "missing", themes: [] };
  private readonly payloads = new Map<string, ThemeExtensionPayload>();
  private readonly ambient: AmbientChannelProvider | undefined;
  private readonly storage: ThemeStorageProvider | undefined;
  private readonly games: Readonly<ThemeExtensionGamesAccess> | undefined;
  private readonly groups: Readonly<ThemeGroupsAccess> | undefined;
  private readonly actions: ThemeActionsProvider | undefined;
  private readonly payloadRequests = new Map<string, Promise<ThemeExtensionPayload>>();
  private readonly active = new Map<string, ActiveRuntime>();
  private readonly pending = new Map<string, number>();
  private readonly surfaces = new Map<string, ThemeExtensionSurface>();
  private readonly classifying = new Set<string>();
  private readonly unclassifiable = new Set<string>();
  private generation = 0;
  private disposed = false;
  private readonly retireTheme: ((cssLoaderName: string, keep: string) => Promise<boolean>) | undefined;
  private readonly retiring = new Set<string>();
  private keyboardOwner: string | null = null;
  private keyboardGroup: ReadonlySet<string> = new Set();

  constructor({
    artwork,
    options,
    client,
    doc,
    qam,
    library,
    navigation,
    evaluate = evaluateThemeExtensionBundle,
    log = (code) => console.warn(`[themes:${code}]`),
    ambient,
    storage,
    games,
    groups,
    actions,
    retireTheme,
  }: ThemeExtensionRuntimeHostOptions) {
    this.retireTheme = retireTheme;
    this.ambient = ambient;
    this.actions = actions;
    this.storage = storage;
    this.games = games;
    this.groups = groups;
    this.artwork = artwork;
    this.options = options ? new ThemeOptionsChannel(options, (code) => this.log(code)) : undefined;
    this.client = client;
    this.doc = doc;
    this.qam = qam ? Object.freeze({
      getDocument: qam.getDocument,
      subscribe: qam.subscribe,
    }) : undefined;
    this.library = library ? Object.freeze({
      launch: library.launch,
      openSettings: library.openSettings,
      openController: library.openController,
      verticalCapsule: library.verticalCapsule,
    }) : undefined;
    this.navigation = navigation ? Object.freeze({
      focus: navigation.focus,
      capture: navigation.capture,
    }) : undefined;
    this.evaluate = evaluate;
    this.log = log;
  }

  reconcile(snapshot: CssLoaderSnapshot): void {
    if (this.disposed) return;
    this.applySnapshot(snapshot);
    this.options?.update(snapshot);
  }

  private applySnapshot(snapshot: CssLoaderSnapshot): void {
    this.snapshot = snapshot;
    this.unclassifiable.clear();
    if (snapshot.status !== "ready" || !snapshot.themes.some((theme) => theme.enabled)) {
      this.invalidatePending();
      this.stop();
      return;
    }
    if (this.descriptors === null) {
      void this.refreshDescriptors();
      return;
    }
    this.reconcileSelection();
  }

  refreshDescriptors(): Promise<void> {
    if (this.disposed) return Promise.resolve();
    if (this.descriptorRequest) return this.descriptorRequest;
    const request = this.client.list().then((descriptors) => {
      if (this.disposed) return;
      this.descriptors = descriptors;
      this.reconcileSelection();
    }).catch(() => {
      if (this.disposed) return;
      this.descriptors = null;
      this.invalidatePending();
      this.stop();
      this.log("extension_list_failed");
    });
    this.descriptorRequest = request;
    const release = () => {
      if (this.descriptorRequest === request) this.descriptorRequest = null;
    };
    void request.then(release, release);
    return request;
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.invalidatePending();
    this.stop();
    this.payloadRequests.clear();
    this.payloads.clear();
  }

  private reconcileSelection(): void {
    if (this.disposed || this.descriptors === null) return;
    const candidates = this.candidates();
    if (candidates.length > 1) {
      const unknown = candidates.filter((candidate) => (
        !this.surfaces.has(candidate.key) && !this.unclassifiable.has(candidate.key)
      ));
      if (unknown.length > 0) {
        for (const candidate of unknown) void this.classify(candidate);
        return;
      }
    }
    const desired = this.desired(candidates);
    for (const [fingerprint, runtime] of [...this.active]) {
      if (desired.has(fingerprint)) continue;
      const successor = runtime.followsOptions()
        ? [...desired.values()].find((selection) => (
          selection.key === runtime.key
          && !this.active.has(selection.fingerprint)
          && runtimeStructure(selection.theme) === runtime.structure
        ))
        : undefined;
      if (successor) {
        this.active.delete(fingerprint);
        this.active.set(successor.fingerprint, runtime);
        this.pending.delete(successor.fingerprint);
      } else {
        this.stop(fingerprint);
      }
    }
    for (const fingerprint of [...this.pending.keys()]) {
      if (!desired.has(fingerprint)) this.pending.delete(fingerprint);
    }
    for (const selection of desired.values()) {
      if (this.active.has(selection.fingerprint) || this.pending.has(selection.fingerprint)) continue;
      const generation = ++this.generation;
      this.pending.set(selection.fingerprint, generation);
      void this.mount(selection, generation);
    }
  }

  private candidates(): RuntimeSelection[] {
    if (this.snapshot.status !== "ready" || this.descriptors === null) return [];
    const selections: RuntimeSelection[] = [];
    for (const theme of this.snapshot.themes) {
      if (!theme.enabled) continue;
      const matches = this.descriptors.filter((descriptor) => (
        descriptor.cssLoaderName === theme.name && descriptor.version === theme.version
      ));
      if (matches.length !== 1) continue;
      const [descriptor] = matches;
      const key = descriptorKey(descriptor);
      selections.push({ descriptor, theme, key, fingerprint: `${key}\0${themeFingerprint(theme)}` });
    }
    return selections;
  }

  // One runtime per surface, except mixed Hooandee themes: each runtime only styles the sections its
  // theme owns, so several home runtimes run together while no section is claimed twice.
  private desired(candidates: readonly RuntimeSelection[]): Map<string, RuntimeSelection> {
    const desired = new Map<string, RuntimeSelection>();
    this.forgetKeyboardThemesOff(candidates);
    if (candidates.length === 1) {
      desired.set(candidates[0].fingerprint, candidates[0]);
      return desired;
    }
    const bySurface = new Map<ThemeExtensionSurface, RuntimeSelection[]>();
    for (const candidate of candidates) {
      const surface = this.surfaces.get(candidate.key);
      if (!surface) continue;
      bySurface.set(surface, [...(bySurface.get(surface) ?? []), candidate]);
    }
    for (const [surface, group] of bySurface) {
      for (const selection of surface === "home" ? homeRuntimes(group) : [this.keyboardRuntime(group)]) {
        desired.set(selection.fingerprint, selection);
      }
    }
    return desired;
  }

  // Only one keyboard theme dresses Steam's keyboard: one turned on next to the owner replaces it, and the one it
  // replaces is turned off in CSS Loader so their styles never stack. With no owner (two on at startup) the first
  // listed wins. The owner is remembered, never re-derived from what is mounted, or the choice would flip each mount.
  private keyboardRuntime(group: readonly RuntimeSelection[]): RuntimeSelection {
    const names = group.map((selection) => selection.theme.name);
    const mountedKeys = new Set([...this.active.values()].map((runtime) => runtime.key));
    const owner = this.keyboardOwner !== null && names.includes(this.keyboardOwner)
      ? this.keyboardOwner
      : group.find((selection) => mountedKeys.has(selection.key) || this.pending.has(selection.fingerprint))?.theme.name ?? null;
    const arrival = owner === null
      ? undefined
      : group.find((selection) => selection.theme.name !== owner && !this.keyboardGroup.has(selection.theme.name));
    const winner = arrival ?? group.find((selection) => selection.theme.name === owner) ?? group[0];
    this.keyboardOwner = winner.theme.name;
    this.keyboardGroup = new Set(names);
    for (const selection of group) {
      if (selection !== winner) this.retire(selection.theme.name, winner.theme.name);
    }
    return winner;
  }

  // Runs on every reconcile, also with a single candidate: a theme turned off leaves the keyboard group and its
  // retirement, so turning it on again counts as a new arrival. One attempt per theme while it stays on: a
  // refusal is logged, not retried on every refresh.
  private forgetKeyboardThemesOff(candidates: readonly RuntimeSelection[]): void {
    const on = new Set(candidates.map((candidate) => candidate.theme.name));
    for (const name of this.retiring) if (!on.has(name)) this.retiring.delete(name);
    this.keyboardGroup = new Set([...this.keyboardGroup].filter((name) => on.has(name)));
    if (this.keyboardOwner !== null && !on.has(this.keyboardOwner)) this.keyboardOwner = null;
  }

  private retire(cssLoaderName: string, keep: string): void {
    if (!this.retireTheme || this.retiring.has(cssLoaderName)) return;
    this.retiring.add(cssLoaderName);
    void this.retireTheme(cssLoaderName, keep)
      .then((retired) => { if (!retired) this.log("keyboard_theme_retire_failed"); })
      .catch(() => this.log("keyboard_theme_retire_failed"));
  }

  private async classify(selection: RuntimeSelection): Promise<void> {
    if (this.classifying.has(selection.key)) return;
    this.classifying.add(selection.key);
    try {
      const payload = await this.load(selection.descriptor);
      if (this.disposed) return;
      const extension = this.evaluate(payload.source);
      if (extension.abiVersion !== payload.abiVersion) throw new Error("Theme extension ABI does not match its receipt");
      this.surfaces.set(selection.key, surfaceOf(extension));
    } catch (error) {
      if (this.disposed) return;
      this.unclassifiable.add(selection.key);
      this.log(error instanceof ThemeExtensionPayloadMismatchError
        ? "extension_payload_mismatch"
        : "extension_evaluation_failed");
    } finally {
      this.classifying.delete(selection.key);
    }
    this.reconcileSelection();
  }

  private async mount(selection: RuntimeSelection, generation: number): Promise<void> {
    let payload: ThemeExtensionPayload;
    try {
      payload = await this.load(selection.descriptor);
    } catch (error) {
      if (this.isCurrent(selection.fingerprint, generation)) {
        this.pending.delete(selection.fingerprint);
        this.log(error instanceof ThemeExtensionPayloadMismatchError
          ? "extension_payload_mismatch"
          : "extension_load_failed");
      } else {
        this.abandon(selection.fingerprint, generation);
      }
      return;
    }
    if (!this.isCurrent(selection.fingerprint, generation)) return this.abandon(selection.fingerprint, generation);
    let extension: ThemeExtensionExport;
    try {
      extension = this.evaluate(payload.source);
      if (extension.abiVersion !== payload.abiVersion) {
        throw new Error("Theme extension ABI does not match its receipt");
      }
      this.surfaces.set(selection.key, surfaceOf(extension));
    } catch {
      if (this.isCurrent(selection.fingerprint, generation)) {
        this.pending.delete(selection.fingerprint);
        this.log("extension_evaluation_failed");
      } else {
        this.abandon(selection.fingerprint, generation);
      }
      return;
    }
    if (!this.isCurrent(selection.fingerprint, generation)) return this.abandon(selection.fingerprint, generation);
    const scope = new MountScope(this.log);
    try {
      const scoped = this.ambient ? scopedAmbientAccess(this.ambient, ambientThemeId(selection.theme.name), selection.descriptor.catalogId) : null;
      const artworkStore = artworkStoreOf(selection.descriptor.catalogId);
      const artwork = artworkStore ? this.artwork?.[artworkStore] : undefined;
      const options = this.options?.forMount(selection.descriptor.catalogId, selection.descriptor.cssLoaderName);
      if (options) scope.track(options.release);
      const sharedContext = {
        theme: freezeTheme(selection.theme),
        document: this.doc,
        host: HOST_DESCRIPTOR,
        ...(scoped ? { ambient: scoped.access } : {}),
        ...(this.storage ? { storage: this.storage.forTheme(selection.descriptor.catalogId) } : {}),
        ...(this.games ? { games: scopedGames(this.games, scope) } : {}),
        ...(this.groups ? { groups: scopedGroups(this.groups, scope) } : {}),
        ...(this.actions ? { actions: scopedActions(this.actions, selection.descriptor.catalogId, scope) } : {}),
        ...(artwork ? { artwork: scopedArtwork(artwork, scope) } : {}),
        ...(options ? { options: options.access } : {}),
      };
      if (scoped) scope.track(() => scoped.release());
      let stop: () => void;
      if (extension.abiVersion === 1) {
        const navigation = this.navigation;
        stop = extension.mount(Object.freeze({
          ...sharedContext,
          ...(navigation ? { navigation: Object.freeze({ focus: navigation.focus }) } : {}),
        }));
      } else {
        if (!this.qam) throw new Error("QAM access is unavailable");
        const qam = this.qam;
        const navigation = this.navigation;
        const context = Object.freeze({
          ...sharedContext,
          qam: Object.freeze({
            getDocument: qam.getDocument,
            subscribe: (listener: (doc: Document) => void) => scope.track(qam.subscribe(listener)),
          }),
          ...(this.library ? { library: this.library } : {}),
          ...(navigation ? {
            navigation: Object.freeze({
              focus: navigation.focus,
              capture: (handler: Parameters<typeof navigation.capture>[0]) => scope.track(navigation.capture(handler)),
            }),
          } : {}),
        });
        const themeStop = extension.mount(context);
        if (typeof themeStop !== "function") throw new Error("Theme extension disposer is invalid");
        stop = () => {
          try {
            themeStop();
          } finally {
            scope.releaseAll();
          }
        };
      }
      if (typeof stop !== "function") throw new Error("Theme extension disposer is invalid");
      if (!this.isCurrent(selection.fingerprint, generation)) {
        try {
          stop();
        } catch {
          this.log("extension_dispose_failed");
        }
        scoped?.release();
        this.abandon(selection.fingerprint, generation);
        return;
      }
      const release = stop;
      stop = () => { try { release(); } finally { scope.releaseAll(); } };
      this.active.set(selection.fingerprint, {
        stop,
        key: selection.key,
        structure: runtimeStructure(selection.theme),
        followsOptions: options ? options.follows : () => false,
      });
      this.pending.delete(selection.fingerprint);
    } catch {
      scope.releaseAll();
      if (this.isCurrent(selection.fingerprint, generation)) {
        this.pending.delete(selection.fingerprint);
        this.log("extension_mount_failed");
      } else {
        this.abandon(selection.fingerprint, generation);
      }
    }
  }

  private load(descriptor: ThemeExtensionDescriptor): Promise<ThemeExtensionPayload> {
    const key = descriptorKey(descriptor);
    const cached = this.payloads.get(key);
    if (cached) return Promise.resolve(cached);
    const existing = this.payloadRequests.get(key);
    if (existing) return existing;
    const request = this.client.load(descriptor.catalogId, descriptor.version).then((payload) => {
      if (!payloadMatches(payload, descriptor)) throw new ThemeExtensionPayloadMismatchError();
      this.payloads.set(key, payload);
      return payload;
    });
    this.payloadRequests.set(key, request);
    const release = () => {
      if (this.payloadRequests.get(key) === request) this.payloadRequests.delete(key);
    };
    void request.then(release, release);
    return request;
  }

  // A mount overtaken by a newer reconcile must not stay "in flight", or that reconcile skips it.
  private abandon(fingerprint: string, generation: number): void {
    if (this.pending.get(fingerprint) !== generation) return;
    this.pending.delete(fingerprint);
    if (!this.disposed) this.reconcileSelection();
  }

  private isCurrent(fingerprint: string, generation: number): boolean {
    return !this.disposed
      && this.pending.get(fingerprint) === generation
      && this.desired(this.candidates()).has(fingerprint);
  }

  private invalidatePending(): void {
    this.generation += 1;
    this.pending.clear();
  }

  private stop(fingerprint?: string): void {
    const targets = fingerprint === undefined ? [...this.active.keys()] : [fingerprint];
    for (const target of targets) {
      const runtime = this.active.get(target);
      if (!runtime) continue;
      this.active.delete(target);
      try {
        runtime.stop();
      } catch {
        this.log("extension_dispose_failed");
      }
    }
  }
}
