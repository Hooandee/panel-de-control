export interface ChannelState {
  owner: "panel" | "theme";
  media: { url: string; kind: "image" | "video" } | null;
  motion: "play" | "pause" | "freeze";
}

export type ChannelFrame = HTMLImageElement | HTMLVideoElement;

export interface ChannelClaim {
  themeId: string;
  name: string;
  surfaces: readonly ("home" | "library")[];
  mode: "yield" | "host";
}

const INITIAL: ChannelState = { owner: "theme", media: null, motion: "pause" };

function sameState(a: ChannelState, b: ChannelState): boolean {
  return a.owner === b.owner && a.motion === b.motion && a.media?.url === b.media?.url && a.media?.kind === b.media?.kind;
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

  publish(next: ChannelState): void {
    if (sameState(this.state, next)) return;
    this.state = next;
    for (const listener of this.stateListeners) listener(next);
  }

  reset(): void {
    this.publish(INITIAL);
  }

  private notifyClaims(): void {
    for (const listener of this.claimListeners) listener();
  }
}
