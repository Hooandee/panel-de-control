export interface ThemeImagePick {
  ref: string;
  url: string;
}

export interface ThemeImageRequest {
  title?: string;
  /** Registers the chosen library ref with the backend; null when it cannot be served. */
  choose(ref: string): Promise<ThemeImagePick | null>;
}

/** Shows the explorer and settles with the registered pick, or null when the user backs out or `signal` aborts. */
export type ThemeImagePicker = (request: ThemeImageRequest, signal: AbortSignal) => Promise<ThemeImagePick | null>;

/** Per screen size bucket ("1280", "1920", "2560"), the URL of that picture. */
export type ThemeImageUrls = Record<string, string>;

/** A listed picture: its URLs and the themes (catalog ids) that keep it; none for one saved before owners existed. */
export interface ThemeImageEntry {
  urls: ThemeImageUrls;
  owners: string[];
}

export interface ThemeImagesBackend {
  list(): Promise<Record<string, ThemeImageEntry>>;
  register(ref: string, owner: string, maxSide: number | null): Promise<{ ref: string; urls: ThemeImageUrls } | { error: string }>;
  keep(owner: string, refs: string[]): Promise<string[]>;
}

export const MAX_KEPT_THEME_IMAGES = 512;
export const MAX_THEME_IMAGE_REF = 512;
/** Long sides Panel serves; the backend's `image_scaler.BUCKETS` must match. */
export const THEME_IMAGE_BUCKETS = [1280, 1920, 2560] as const;
const REFRESH_MS = 30_000;
const RETRY_MS = 5_000;

/** Snaps the screen's long side up to a served size, never above 1440p; unknown or invalid means the cap. */
export function themeImageBucket(maxSide?: unknown): number {
  const cap = THEME_IMAGE_BUCKETS[THEME_IMAGE_BUCKETS.length - 1];
  if (typeof maxSide !== "number" || !Number.isFinite(maxSide) || maxSide <= 0) return cap;
  return THEME_IMAGE_BUCKETS.find((bucket) => maxSide <= bucket) ?? cap;
}

export function validThemeImageRef(ref: unknown): ref is string {
  return typeof ref === "string" && ref.length > 0 && ref.length <= MAX_THEME_IMAGE_REF;
}

/** The refs a theme says it keeps, deduplicated and sorted; null when the input is not a bounded list of refs. */
export function keptThemeImageRefs(refs: unknown): string[] | null {
  if (!Array.isArray(refs) || refs.length > MAX_KEPT_THEME_IMAGES || !refs.every(validThemeImageRef)) return null;
  return [...new Set(refs)].sort();
}

function validUrls(urls: unknown): urls is ThemeImageUrls {
  return Boolean(urls) && typeof urls === "object" && Object.values(urls as object).every((url) => typeof url === "string" && url.length > 0);
}

function validEntry(ref: string, entry: unknown): entry is ThemeImageEntry {
  if (!validThemeImageRef(ref) || !entry || typeof entry !== "object") return false;
  const { urls, owners } = entry as Partial<ThemeImageEntry>;
  return validUrls(urls) && Array.isArray(owners) && owners.every((owner) => typeof owner === "string");
}

function sameUrls(a: ThemeImageUrls | undefined, b: ThemeImageUrls): boolean {
  if (!a) return false;
  const keys = Object.keys(b);
  return keys.length === Object.keys(a).length && keys.every((key) => a[key] === b[key]);
}

interface HeldImage {
  urls: ThemeImageUrls;
  owners: Set<string>;
}

function sameEntry(a: HeldImage | undefined, b: HeldImage): boolean {
  return Boolean(a) && sameUrls(a!.urls, b.urls) && a!.owners.size === b.owners.size && [...b.owners].every((owner) => a!.owners.has(owner));
}

// A theme reads only the pictures it keeps (or old ones no theme has claimed yet), so a ref is not a key
// to another theme's choices.
function heldBy(entry: HeldImage | undefined, owner: string): entry is HeldImage {
  return Boolean(entry) && (entry!.owners.size === 0 || entry!.owners.has(owner));
}

/**
 * Pictures theme runtimes chose through Ambiente's explorer. `url()` is synchronous because themes call it on
 * every render: it answers from memory and, at most every 30 s, refreshes from the backend so a deleted file
 * stops resolving and the per-boot media server URLs are current. A size that needs a smaller copy gets a URL
 * the media server scales on its first request and then serves from its cache.
 */
export class ThemeImages {
  private images = new Map<string, HeldImage>();
  private listeners = new Set<() => void>();
  private loading: Promise<void> | null = null;
  private nextRefreshAt = 0;
  private picking = false;
  private stopped = false;
  private kept = new Map<string, string>();
  // Registrations and kept sets reach the backend in the order themes made them, so a layout save sent
  // before a pick cannot forget the picture that pick just registered.
  private ordered: Promise<unknown> = Promise.resolve();

  constructor(
    private readonly backend: ThemeImagesBackend,
    private readonly picker: ThemeImagePicker,
    private readonly now: () => number = () => Date.now(),
  ) {}

  url(owner: string, ref: string, maxSide?: number): string | null {
    if (!validThemeImageRef(ref) || this.stopped) return null;
    if (this.now() >= this.nextRefreshAt) void this.refresh();
    const entry = this.images.get(ref);
    return heldBy(entry, owner) ? entry.urls[String(themeImageBucket(maxSide))] ?? null : null;
  }

  refresh(): Promise<void> {
    if (this.stopped) return Promise.resolve();
    if (this.loading) return this.loading;
    this.nextRefreshAt = this.now() + REFRESH_MS;
    const request = this.backend.list().then((listed) => {
      if (this.stopped) return;
      const next = new Map<string, HeldImage>();
      for (const [ref, entry] of Object.entries(listed && typeof listed === "object" ? listed : {})) {
        if (validEntry(ref, entry)) next.set(ref, { urls: { ...entry.urls }, owners: new Set(entry.owners) });
      }
      if (next.size === this.images.size && [...next].every(([ref, entry]) => sameEntry(this.images.get(ref), entry))) return;
      this.images = next;
      this.notify();
    }, () => {
      this.nextRefreshAt = this.now() + RETRY_MS;
    }).finally(() => {
      if (this.loading === request) this.loading = null;
    });
    this.loading = request;
    return request;
  }

  /** One explorer at a time: a second call while one is open settles null right away. */
  async pick(owner: string, options: { title?: string; maxSide?: number }, signal: AbortSignal = new AbortController().signal): Promise<ThemeImagePick | null> {
    if (this.picking || this.stopped || signal.aborted || !owner) return null;
    this.picking = true;
    try {
      const { title, maxSide } = options;
      return await this.picker({ ...(title ? { title } : {}), choose: (ref) => this.register(ref, owner, maxSide) }, signal);
    } catch {
      return null;
    } finally {
      this.picking = false;
    }
  }

  /**
   * `owner` still shows exactly `refs`: the backend forgets every other picture of that owner (unless another
   * theme keeps it) and deletes their copies. Themes call this on every layout save, so an unchanged set never
   * reaches the backend, and calls run in order with registrations. Invalid input is ignored.
   */
  keep(owner: string, refs: unknown): void {
    const set = keptThemeImageRefs(refs);
    if (this.stopped || !owner || !set) return;
    const signature = set.join("\n");
    if (this.kept.get(owner) === signature) return;
    this.kept.set(owner, signature);
    this.inOrder(async () => {
      try {
        const dropped = await this.backend.keep(owner, set);
        if (this.stopped || !Array.isArray(dropped)) return;
        this.applyKeep(owner, new Set(set), dropped);
      } catch {
        if (this.kept.get(owner) === signature) this.kept.delete(owner);
      }
    });
  }

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  }

  stop(): void {
    this.stopped = true;
    this.listeners.clear();
    this.images.clear();
  }

  private inOrder<T>(task: () => Promise<T>): Promise<T | null> {
    const run = this.ordered.then(() => (this.stopped ? null : task()));
    this.ordered = run.catch(() => undefined);
    return run.catch(() => null);
  }

  // Mirrors what the backend just did, so the owner stops reading a picture it no longer keeps right away.
  private applyKeep(owner: string, refs: ReadonlySet<string>, dropped: readonly unknown[]): void {
    let changed = false;
    for (const ref of dropped) if (typeof ref === "string") changed = this.images.delete(ref) || changed;
    for (const [ref, entry] of this.images) {
      if (refs.has(ref)) {
        if (entry.owners.size === 0) {
          entry.owners.add(owner);
          changed = true;
        }
      } else if (entry.owners.delete(owner)) {
        changed = true;
      }
    }
    if (changed) this.notify();
  }

  private async register(ref: string, owner: string, maxSide?: number): Promise<ThemeImagePick | null> {
    const side = typeof maxSide === "number" && Number.isFinite(maxSide) && maxSide > 0 ? maxSide : null;
    const result = await this.inOrder(() => this.backend.register(ref, owner, side));
    if (this.stopped || !result || "error" in result || !validThemeImageRef(result.ref) || !validUrls(result.urls)) return null;
    const url = result.urls[String(themeImageBucket(maxSide))];
    if (!url) return null;
    this.kept.delete(owner);
    const previous = this.images.get(result.ref);
    const next: HeldImage = { urls: { ...result.urls }, owners: new Set([...(previous?.owners ?? []), owner]) };
    if (!sameEntry(previous, next)) {
      this.images.set(result.ref, next);
      this.notify();
    }
    return { ref: result.ref, url };
  }

  private notify(): void {
    for (const listener of [...this.listeners]) {
      try { listener(); } catch { /* one theme's listener must not starve the others */ }
    }
  }
}
