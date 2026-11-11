import type { ThemeImagePick } from "./themeImages";

/** What the channel needs from the theme picture registry (`ThemeImages`). */
export interface ChannelImages {
  pick(owner: string, options: { title?: string; maxSide?: number }, signal?: AbortSignal): Promise<ThemeImagePick | null>;
  url(owner: string, ref: string, maxSide?: number): string | null;
  keep(owner: string, refs: unknown): void;
  subscribe(listener: () => void): () => void;
}

export interface ChannelState {
  owner: "panel" | "theme";
  media: { url: string; kind: "image" | "video" } | null;
  motion: "play" | "pause" | "freeze";
  music?: { playing: boolean };
}

export type ChannelFrame = HTMLImageElement | HTMLVideoElement;

export interface ChannelClaim {
  themeId: string;
  name: string;
  surfaces: readonly ("home" | "library")[];
  mode: "yield" | "host";
}

/** Steam app ids (store games and non-Steam shortcuts) are unsigned 32-bit integers. */
export function normalizeAppId(value: unknown): string | null {
  const text = typeof value === "number" ? String(value) : typeof value === "string" ? value.trim() : "";
  if (!/^\d{1,10}$/.test(text)) return null;
  const id = Number(text);
  return id > 0 && id < 2 ** 32 ? String(id) : null;
}

const INITIAL: ChannelState = { owner: "theme", media: null, motion: "pause", music: { playing: false } };

function sameState(a: ChannelState, b: ChannelState): boolean {
  return a.owner === b.owner && a.motion === b.motion && a.media?.url === b.media?.url && a.media?.kind === b.media?.kind
    && a.music?.playing === b.music?.playing;
}

/**
 * The theme side of Ambiente: runtimes claim the background and read what Panel wants painted.
 * Structurally matches the theme host's AmbientChannelProvider without importing that domain.
 */
export class AmbientThemeChannel {
  private claims = new Map<string, ChannelClaim>();
  private state: ChannelState = INITIAL;
  private stateListeners = new Set<(state: ChannelState) => void>();
  private claimListeners = new Set<() => void>();
  private frameSource: () => ChannelFrame | null = () => null;
  private selections = new Map<string, { appid: string | null }>();
  private selectionListeners = new Set<() => void>();
  private images: ChannelImages | null = null;
  private releaseImages: (() => void) | null = null;
  private imageListeners = new Set<() => void>();

  setImages(images: ChannelImages | null): void {
    this.releaseImages?.();
    this.images = images;
    this.releaseImages = images ? images.subscribe(() => this.notifyImages()) : null;
    this.notifyImages();
  }

  /** Opens Ambiente's photo explorer for a theme; null when Panel cannot offer it or the user backs out. */
  pickImage(owner: string, options: { title?: string; maxSide?: number }, signal?: AbortSignal): Promise<ThemeImagePick | null> {
    return this.images ? this.images.pick(owner, options, signal) : Promise.resolve(null);
  }

  keepImages(owner: string, refs: readonly string[]): void {
    this.images?.keep(owner, refs);
  }

  imageUrl(owner: string, ref: string, maxSide?: number): string | null {
    return this.images?.url(owner, ref, maxSide) ?? null;
  }

  subscribeImages(listener: () => void): () => void {
    this.imageListeners.add(listener);
    return () => { this.imageListeners.delete(listener); };
  }

  private notifyImages(): void {
    for (const listener of [...this.imageListeners]) {
      try { listener(); } catch { /* a theme's listener must not break the others */ }
    }
  }

  /** The game a theme selected on its own Home (`null`: none). Releasing hands it back to Steam's carousel. */
  select(themeId: string, appid: string | null): () => void {
    const entry = { appid: normalizeAppId(appid) };
    const previous = this.selections.get(themeId);
    this.selections.set(themeId, entry);
    if (!previous || previous.appid !== entry.appid) this.notifySelection();
    return () => {
      if (this.selections.get(themeId) !== entry) return;
      this.selections.delete(themeId);
      this.notifySelection();
    };
  }

  themeSelection(): { themeId: string; appid: string | null } | undefined {
    const first = this.selections.entries().next().value;
    return first ? { themeId: first[0], appid: first[1].appid } : undefined;
  }

  onSelectionChanged(listener: () => void): () => void {
    this.selectionListeners.add(listener);
    return () => this.selectionListeners.delete(listener);
  }

  claim(themeId: string, options: { name: string; surfaces: readonly ("home" | "library")[]; mode: "yield" | "host" }): () => void {
    const claim: ChannelClaim = { themeId, name: options.name, surfaces: options.surfaces, mode: options.mode };
    this.claims.set(themeId, claim);
    this.notifyClaims();
    return () => {
      if (this.claims.get(themeId) !== claim) return;
      this.claims.delete(themeId);
      this.notifyClaims();
    };
  }

  getState(): ChannelState {
    return this.state;
  }

  subscribe(listener: (state: ChannelState) => void): () => void {
    this.stateListeners.add(listener);
    return () => this.stateListeners.delete(listener);
  }

  /** What Panel is painting right now, for themes that mirror the background (reflections, tints). */
  frame(): ChannelFrame | null {
    return this.state.owner === "panel" ? this.frameSource() : null;
  }

  setFrameSource(source: () => ChannelFrame | null): void {
    this.frameSource = source;
  }

  activeClaim(): ChannelClaim | null {
    return this.claims.values().next().value ?? null;
  }

  onClaimsChanged(listener: () => void): () => void {
    this.claimListeners.add(listener);
    return () => this.claimListeners.delete(listener);
  }

  /** A background change keeps the music as it was unless it says otherwise. */
  publish(next: ChannelState): void {
    if (!next.music && this.state.music) next = { ...next, music: this.state.music };
    if (sameState(this.state, next)) return;
    this.state = next;
    for (const listener of this.stateListeners) listener(next);
  }

  /** Whether Ambiente's music is audibly playing, so a theme can fade its own music around it. */
  setMusicPlaying(playing: boolean): void {
    this.publish({ ...this.state, music: { playing } });
  }

  reset(): void {
    this.publish(INITIAL);
  }

  private notifyClaims(): void {
    for (const listener of this.claimListeners) listener();
  }

  private notifySelection(): void {
    for (const listener of this.selectionListeners) listener();
  }
}
