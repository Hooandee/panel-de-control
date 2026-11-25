import type { CssLoaderPatch, CssLoaderSnapshot, CssLoaderTheme } from "../cssLoaderTypes";
import { sectionKeyOf } from "../sectionOwnership";

export interface ThemeOptionState {
  value: string;
  values: readonly string[];
  type: string;
}

/**
 * The mounted theme's own CSS Loader options. A runtime that subscribes takes over live option changes: Panel then
 * stops remounting it when a value changes (a change to an «Estilizar …» section still remounts), and
 * `context.theme.patches` stays the snapshot taken at mount, so read values from `get()`.
 * «Estilizar …» options are read-only here: switching a section moves it between themes, which only the user does.
 */
export interface ThemeOptionsAccess {
  /** This theme's options by patch name: current value, allowed values and CSS Loader type. Always live. */
  get(): Readonly<Record<string, Readonly<ThemeOptionState>>>;
  /**
   * Sets one option through the same CSS Loader writes as Panel's Temas screen, without blocking that screen or
   * showing errors there. Resolves false when the patch or value is not this theme's, the patch is an «Estilizar …»
   * section, CSS Loader fails, or the runtime has unmounted. Writes are serialized and coalesced per patch:
   * a call overtaken by a newer value for the same patch resolves with the result of that newer write.
   */
  set(patch: string, value: string): Promise<boolean>;
  /** Several options in one Panel operation; nothing is written when any patch or value is invalid. Not atomic in CSS Loader. */
  setMany?(values: Readonly<Record<string, string>>): Promise<boolean>;
  /** Called after any of this theme's option values change: from Panel's Temas screen, CSS Loader, or set(). */
  subscribe(listener: () => void): () => void;
}

/** What Panel provides: a runtime's own option writes, keyed by catalog id, serialized with the Temas screen's. */
export interface ThemeOptionsWriter {
  setPatches(catalogId: string, values: Readonly<Record<string, string>>): Promise<boolean>;
  /** True while a user's theme operation holds Panel's lock, so a refused write is worth retrying. */
  busy?(): boolean;
}

export type ThemeOptionsLogCode = "options_write_failed" | "options_listener_failed";

interface PendingWrite {
  value: string;
  resolvers: ((ok: boolean) => void)[];
}

const BUSY_RETRY_MS = 150;
const BUSY_RETRY_LIMIT = 40;
const MAX_TEXT_LENGTH = 256;

function editable(patch: CssLoaderPatch): boolean {
  return patch.type !== "none" && patch.type !== "unsupported";
}

function valuesFingerprint(theme: CssLoaderTheme | undefined): string {
  if (!theme) return "";
  return JSON.stringify(theme.patches.map((patch) => [patch.name, patch.value, patch.options]));
}

function optionsOf(theme: CssLoaderTheme | undefined): Readonly<Record<string, Readonly<ThemeOptionState>>> {
  const result: Record<string, Readonly<ThemeOptionState>> = {};
  for (const patch of theme?.patches ?? []) {
    if (!editable(patch)) continue;
    result[patch.name] = Object.freeze({ value: patch.value, values: Object.freeze([...patch.options]), type: patch.type });
  }
  return Object.freeze(result);
}

/** One write queue per theme, kept across remounts so a write in flight still lands. */
class ThemeOptionsQueue {
  private readonly pending = new Map<string, PendingWrite>();
  private draining = false;

  constructor(
    private readonly catalogId: string,
    private readonly writer: ThemeOptionsWriter,
    private readonly currentValue: (patch: string) => string | undefined,
    private readonly log: (code: ThemeOptionsLogCode) => void,
    private readonly wait: (ms: number) => Promise<void>,
  ) {}

  enqueue(patch: string, value: string): Promise<boolean> {
    return new Promise((resolve) => {
      const existing = this.pending.get(patch);
      if (existing) {
        existing.value = value;
        existing.resolvers.push(resolve);
      } else {
        this.pending.set(patch, { value, resolvers: [resolve] });
      }
      void this.drain();
    });
  }

  private async drain(): Promise<void> {
    if (this.draining) return;
    this.draining = true;
    try {
      // Calls made in the same tick (setMany, a burst of set()) leave as one batch.
      await Promise.resolve();
      while (this.pending.size > 0) {
        const batch = new Map(this.pending);
        this.pending.clear();
        let ok = false;
        try {
          ok = await this.write(new Map([...batch].map(([patch, entry]) => [patch, entry.value])));
        } catch {
          ok = false;
        }
        if (!ok) this.log("options_write_failed");
        for (const entry of batch.values()) for (const resolve of entry.resolvers) resolve(ok);
      }
    } finally {
      this.draining = false;
    }
  }

  private async write(values: Map<string, string>): Promise<boolean> {
    const changes = Object.fromEntries([...values].filter(([patch, value]) => this.currentValue(patch) !== value));
    if (Object.keys(changes).length === 0) return true;
    return this.retryWhileBusy(() => this.writer.setPatches(this.catalogId, changes));
  }

  // Panel refuses a theme write while another theme operation (Temas, an activation, a refresh's recovery) runs.
  private async retryWhileBusy(write: () => Promise<boolean>): Promise<boolean> {
    for (let attempt = 0; ; attempt += 1) {
      if (await write()) return true;
      if (attempt >= BUSY_RETRY_LIMIT || !this.writer.busy?.()) return false;
      await this.wait(BUSY_RETRY_MS);
    }
  }
}

/** Live options for every mounted theme, fed from the same CSS Loader snapshot Panel's Temas screen shows. */
export class ThemeOptionsChannel {
  private snapshot: CssLoaderSnapshot = { status: "missing", themes: [] };
  private readonly queues = new Map<string, ThemeOptionsQueue>();
  private readonly listeners = new Map<string, Set<() => void>>();
  private readonly seen = new Map<string, string>();
  private readonly cached = new Map<string, { snapshot: CssLoaderSnapshot; options: ReturnType<typeof optionsOf> }>();

  constructor(
    private readonly writer: ThemeOptionsWriter,
    private readonly log: (code: ThemeOptionsLogCode) => void,
    private readonly wait: (ms: number) => Promise<void> = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  ) {}

  update(snapshot: CssLoaderSnapshot): void {
    this.snapshot = snapshot;
    for (const [themeName, listeners] of this.listeners) {
      const fingerprint = valuesFingerprint(this.theme(themeName));
      if (this.seen.get(themeName) === fingerprint) continue;
      this.seen.set(themeName, fingerprint);
      for (const listener of [...listeners]) {
        try {
          listener();
        } catch {
          this.log("options_listener_failed");
        }
      }
    }
  }

  /**
   * Access scoped to one mount of one theme. `follows()` is true while the runtime holds at least one options
   * subscription: then it follows value changes itself and the host need not remount it.
   */
  forMount(catalogId: string, themeName: string): { access: Readonly<ThemeOptionsAccess>; release(): void; follows(): boolean } {
    let released = false;
    // One entry per subscription, so subscribing the same listener twice needs two unsubscribes.
    const own = new Set<{ listener: () => void }>();
    const valid = (patch: unknown, value: unknown): patch is string => {
      if (typeof patch !== "string" || typeof value !== "string") return false;
      if (patch.length > MAX_TEXT_LENGTH || value.length > MAX_TEXT_LENGTH) return false;
      if (sectionKeyOf(patch) !== null) return false;
      const found = this.theme(themeName)?.patches.find((candidate) => candidate.name === patch);
      return Boolean(found && editable(found) && found.options.includes(value));
    };
    const access: ThemeOptionsAccess = {
      get: () => this.options(themeName),
      set: (patch, value) => {
        if (released || !valid(patch, value)) return Promise.resolve(false);
        return this.queue(catalogId, themeName).enqueue(patch, value);
      },
      setMany: (values) => {
        if (released || typeof values !== "object" || values === null) return Promise.resolve(false);
        const entries = Object.entries(values);
        if (entries.length === 0) return Promise.resolve(true);
        if (!entries.every(([patch, value]) => valid(patch, value))) return Promise.resolve(false);
        const queue = this.queue(catalogId, themeName);
        return Promise.all(entries.map(([patch, value]) => queue.enqueue(patch, value))).then((results) => results.every(Boolean));
      },
      subscribe: (listener) => {
        if (released || typeof listener !== "function") return () => {};
        const subscription = { listener: () => listener() };
        let listeners = this.listeners.get(themeName);
        if (!listeners) {
          listeners = new Set();
          this.listeners.set(themeName, listeners);
          this.seen.set(themeName, valuesFingerprint(this.theme(themeName)));
        }
        listeners.add(subscription.listener);
        own.add(subscription);
        let active = true;
        return () => {
          if (!active) return;
          active = false;
          own.delete(subscription);
          this.removeListener(themeName, subscription.listener);
        };
      },
    };
    return {
      access: Object.freeze(access),
      release: () => {
        released = true;
        for (const subscription of own) this.removeListener(themeName, subscription.listener);
        own.clear();
      },
      follows: () => own.size > 0,
    };
  }

  private removeListener(themeName: string, listener: () => void): void {
    const listeners = this.listeners.get(themeName);
    if (!listeners) return;
    listeners.delete(listener);
    if (listeners.size === 0) {
      this.listeners.delete(themeName);
      this.seen.delete(themeName);
    }
  }

  private theme(themeName: string): CssLoaderTheme | undefined {
    return this.snapshot.status === "ready" ? this.snapshot.themes.find((theme) => theme.name === themeName) : undefined;
  }

  private options(themeName: string): ReturnType<typeof optionsOf> {
    const cached = this.cached.get(themeName);
    if (cached?.snapshot === this.snapshot) return cached.options;
    const options = optionsOf(this.theme(themeName));
    this.cached.set(themeName, { snapshot: this.snapshot, options });
    return options;
  }

  private queue(catalogId: string, themeName: string): ThemeOptionsQueue {
    let queue = this.queues.get(catalogId);
    if (!queue) {
      queue = new ThemeOptionsQueue(
        catalogId,
        this.writer,
        (patch) => this.theme(themeName)?.patches.find((candidate) => candidate.name === patch)?.value,
        this.log,
        this.wait,
      );
      this.queues.set(catalogId, queue);
    }
    return queue;
  }
}

interface ThemesClientWrites {
  setRuntimePatches(themeId: string, values: Readonly<Record<string, string>>): Promise<boolean>;
  getSnapshot(): { operation: unknown };
}

/** The same ThemesClient as the Temas screen, so its snapshot stays in step, through its quiet runtime path. */
export function themesClientOptionsWriter(client: ThemesClientWrites): ThemeOptionsWriter {
  return Object.freeze({
    setPatches: (catalogId: string, values: Readonly<Record<string, string>>) => client.setRuntimePatches(catalogId, values),
    busy: () => client.getSnapshot().operation !== null,
  });
}
