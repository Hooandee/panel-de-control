import type { CssLoaderPatch, CssLoaderSnapshot, CssLoaderTheme } from "../cssLoaderTypes";
import type {
  ThemeExtensionClient,
  ThemeExtensionDescriptor,
  ThemeExtensionPayload,
} from "../themeExtensionClient";

export interface ThemeExtensionHostDescriptor {
  abiVersion: 1;
}

export interface ThemeExtensionMountContext {
  theme: Readonly<CssLoaderTheme>;
  document: Document;
  host: Readonly<ThemeExtensionHostDescriptor>;
}

export interface ThemeExtensionExport {
  abiVersion: 1;
  mount(context: ThemeExtensionMountContext): () => void;
}

type ExtensionEvaluator = (source: string) => ThemeExtensionExport;
type ExtensionLogCode =
  | "extension_list_failed"
  | "extension_load_failed"
  | "extension_payload_mismatch"
  | "extension_evaluation_failed"
  | "extension_mount_failed"
  | "extension_dispose_failed";

interface ThemeExtensionRuntimeHostOptions {
  client: ThemeExtensionClient;
  doc: Document;
  evaluate?: ExtensionEvaluator;
  log?(code: ExtensionLogCode): void;
}

interface RuntimeSelection {
  descriptor: ThemeExtensionDescriptor;
  theme: CssLoaderTheme;
  fingerprint: string;
}

class ThemeExtensionPayloadMismatchError extends Error {}

const HOST_DESCRIPTOR: Readonly<ThemeExtensionHostDescriptor> = Object.freeze({ abiVersion: 1 });

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
    || !exactKeys(extension, ["abiVersion", "mount"])
    || Reflect.get(extension, "abiVersion") !== 1
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
  private readonly evaluate: ExtensionEvaluator;
  private readonly log: (code: ExtensionLogCode) => void;
  private descriptors: readonly ThemeExtensionDescriptor[] | null = null;
  private descriptorRequest: Promise<void> | null = null;
  private snapshot: CssLoaderSnapshot = { status: "missing", themes: [] };
  private readonly payloads = new Map<string, ThemeExtensionPayload>();
  private readonly payloadRequests = new Map<string, Promise<ThemeExtensionPayload>>();
  private activeFingerprint: string | null = null;
  private pendingFingerprint: string | null = null;
  private stopActive: (() => void) | null = null;
  private generation = 0;
  private disposed = false;

  constructor({
    client,
    doc,
    evaluate = evaluateThemeExtensionBundle,
    log = (code) => console.warn(`[themes:${code}]`),
  }: ThemeExtensionRuntimeHostOptions) {
    this.client = client;
    this.doc = doc;
    this.evaluate = evaluate;
    this.log = log;
  }

  reconcile(snapshot: CssLoaderSnapshot): void {
    if (this.disposed) return;
    this.snapshot = snapshot;
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
      this.descriptors = [];
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
    const selection = this.select();
    if (!selection) {
      this.invalidatePending();
      this.stop();
      return;
    }
    if (
      selection.fingerprint === this.activeFingerprint
      || selection.fingerprint === this.pendingFingerprint
    ) return;
    this.invalidatePending();
    this.stop();
    this.pendingFingerprint = selection.fingerprint;
    const generation = this.generation;
    void this.mount(selection, generation);
  }

  private select(): RuntimeSelection | null {
    if (this.snapshot.status !== "ready" || this.descriptors === null) return null;
    const matches: Array<{ descriptor: ThemeExtensionDescriptor; theme: CssLoaderTheme }> = [];
    for (const theme of this.snapshot.themes) {
      if (!theme.enabled) continue;
      for (const descriptor of this.descriptors) {
        if (descriptor.cssLoaderName === theme.name && descriptor.version === theme.version) {
          matches.push({ descriptor, theme });
        }
      }
    }
    if (matches.length !== 1) return null;
    const [{ descriptor, theme }] = matches;
    return {
      descriptor,
      theme,
      fingerprint: `${descriptorKey(descriptor)}\0${themeFingerprint(theme)}`,
    };
  }

  private async mount(selection: RuntimeSelection, generation: number): Promise<void> {
    let payload: ThemeExtensionPayload;
    try {
      payload = await this.load(selection.descriptor);
    } catch (error) {
      if (this.isCurrent(selection.fingerprint, generation)) {
        this.pendingFingerprint = null;
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
    } catch {
      if (this.isCurrent(selection.fingerprint, generation)) {
        this.pendingFingerprint = null;
        this.log("extension_evaluation_failed");
      }
      return;
    }
    if (!this.isCurrent(selection.fingerprint, generation)) return;
    try {
      const stop = extension.mount(Object.freeze({
        theme: freezeTheme(selection.theme),
        document: this.doc,
        host: HOST_DESCRIPTOR,
      }));
      if (typeof stop !== "function") throw new Error("Theme extension disposer is invalid");
      if (!this.isCurrent(selection.fingerprint, generation)) {
        try {
          stop();
        } catch {
          this.log("extension_dispose_failed");
        }
        return;
      }
      this.stopActive = stop;
      this.activeFingerprint = selection.fingerprint;
      this.pendingFingerprint = null;
    } catch {
      if (this.isCurrent(selection.fingerprint, generation)) {
        this.pendingFingerprint = null;
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
      && this.generation === generation
      && this.pendingFingerprint === fingerprint
      && this.select()?.fingerprint === fingerprint;
  }

  private invalidatePending(): void {
    this.generation += 1;
    this.pendingFingerprint = null;
  }

  private stop(): void {
    const stop = this.stopActive;
    this.stopActive = null;
    this.activeFingerprint = null;
    if (!stop) return;
    try {
      stop();
    } catch {
      this.log("extension_dispose_failed");
    }
  }
}
