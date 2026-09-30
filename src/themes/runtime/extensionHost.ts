import type { CssLoaderPatch, CssLoaderSnapshot, CssLoaderTheme } from "../cssLoaderTypes";
import type {
  ThemeExtensionClient,
  ThemeExtensionDescriptor,
  ThemeExtensionPayload,
} from "../themeExtensionClient";
import type { ThemeExtensionLibraryAccess } from "./libraryAccess";
import type { ThemeExtensionNavigationAccess } from "./navigationAccess";
import { SECTION_ON, sectionKeyOf } from "../sectionOwnership";

export interface ThemeExtensionHostDescriptor {
  abiVersion: 1;
}

export interface ThemeExtensionQamAccess {
  getDocument(): Document | null;
  subscribe(listener: (doc: Document) => void): () => void;
}

export interface ThemeExtensionMountContextV1 {
  theme: Readonly<CssLoaderTheme>;
  document: Document;
  host: Readonly<ThemeExtensionHostDescriptor>;
  qam?: never;
  navigation?: Readonly<Pick<ThemeExtensionNavigationAccess, "focus">>;
}

export interface ThemeExtensionMountContextV2 {
  theme: Readonly<CssLoaderTheme>;
  document: Document;
  host: Readonly<ThemeExtensionHostDescriptor>;
  qam: Readonly<ThemeExtensionQamAccess>;
  library?: Readonly<ThemeExtensionLibraryAccess>;
  navigation?: Readonly<ThemeExtensionNavigationAccess>;
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
  | "extension_release_failed";

interface ThemeExtensionRuntimeHostOptions {
  client: ThemeExtensionClient;
  doc: Document;
  qam?: ThemeExtensionQamAccess;
  library?: ThemeExtensionLibraryAccess;
  navigation?: ThemeExtensionNavigationAccess;
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
}

class ThemeExtensionPayloadMismatchError extends Error {}

const HOST_DESCRIPTOR: Readonly<ThemeExtensionHostDescriptor> = Object.freeze({ abiVersion: 1 });

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

function freezeTheme(theme: CssLoaderTheme): Readonly<CssLoaderTheme> {
  return Object.freeze({ ...theme, patches: Object.freeze(theme.patches.map(freezePatch)) });
}

function themeFingerprint(theme: CssLoaderTheme): string {
  const patches = theme.patches
    .map((patch) => [patch.name, patch.value] as const)
    .sort(([left], [right]) => left.localeCompare(right, "en"));
  return JSON.stringify({ version: theme.version, patches });
}

function claimedSections(theme: CssLoaderTheme): string[] | null {
  const sections = theme.patches.filter((patch) => sectionKeyOf(patch.name) !== null);
  if (sections.length === 0) return null;
  return sections.filter((patch) => patch.value === SECTION_ON).map((patch) => sectionKeyOf(patch.name)!);
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
  private readonly payloadRequests = new Map<string, Promise<ThemeExtensionPayload>>();
  private readonly active = new Map<string, ActiveRuntime>();
  private readonly pending = new Map<string, number>();
  private readonly surfaces = new Map<string, ThemeExtensionSurface>();
  private readonly classifying = new Set<string>();
  private readonly unclassifiable = new Set<string>();
  private generation = 0;
  private disposed = false;

  constructor({
    client,
    doc,
    qam,
    library,
    navigation,
    evaluate = evaluateThemeExtensionBundle,
    log = (code) => console.warn(`[themes:${code}]`),
  }: ThemeExtensionRuntimeHostOptions) {
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
    for (const fingerprint of [...this.active.keys()]) {
      if (!desired.has(fingerprint)) this.stop(fingerprint);
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
      for (const selection of surface === "home" ? homeRuntimes(group) : group.length === 1 ? group : []) {
        desired.set(selection.fingerprint, selection);
      }
    }
    return desired;
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
      }
      return;
    }
    if (!this.isCurrent(selection.fingerprint, generation)) return;
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
      }
      return;
    }
    if (!this.isCurrent(selection.fingerprint, generation)) return;
    const scope = new MountScope(this.log);
    try {
      const sharedContext = {
        theme: freezeTheme(selection.theme),
        document: this.doc,
        host: HOST_DESCRIPTOR,
      };
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
        return;
      }
      this.active.set(selection.fingerprint, { stop });
      this.pending.delete(selection.fingerprint);
    } catch {
      scope.releaseAll();
      if (this.isCurrent(selection.fingerprint, generation)) {
        this.pending.delete(selection.fingerprint);
        this.log("extension_mount_failed");
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
