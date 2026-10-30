export interface GameTrailer {
  url: string;
  poster: string;
  title: string;
}

export interface GameTheme {
  url: string;
  title: string;
  artist: string;
}

export interface GameMedia {
  trailer: GameTrailer | null;
  theme: GameTheme | null;
}

/** Resting on a game this long starts its trailer and music; skimming past games stays quiet. */
export const SETTLE_MS = 1500;

/**
 * Follows the game selected on Home and, once the selection settles, looks up its official media.
 * Only the settled game's media is ever reported, so a late answer for a game already left is dropped.
 */
export class GameMediaDirector {
  private selected: string | null = null;
  private resolved: string | null = null;
  private settled: { appid: string; media: GameMedia } | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private readonly cache = new Map<string, GameMedia>();

  private readonly prefetching = new Set<string>();

  constructor(
    private readonly lookup: (appid: string) => Promise<GameMedia>,
    private readonly onChange: () => void,
    private readonly neighbors: () => string[] = () => [],
  ) {}

  select(appid: string | null): void {
    if (appid === this.selected) return;
    this.selected = appid;
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
    if (this.settled) {
      this.settled = null;
      this.onChange();
    }
    if (!appid) return;
    this.timer = setTimeout(() => {
      this.timer = null;
      void this.resolve(appid);
    }, SETTLE_MS);
  }

  current(): { appid: string; media: GameMedia } | null {
    return this.settled;
  }

  /** A game is selected and its media is not known yet: the settle wait or the lookup is running. */
  pending(): boolean {
    return this.selected !== null && this.resolved !== this.selected;
  }

  dispose(): void {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
    this.selected = null;
    this.resolved = null;
    this.settled = null;
  }

  private async resolve(appid: string): Promise<void> {
    const media = this.cache.get(appid) ?? await this.lookup(appid).catch(() => ({ trailer: null, theme: null }));
    this.cache.set(appid, media);
    if (appid !== this.selected) return;
    this.resolved = appid;
    if (media.trailer || media.theme) this.settled = { appid, media };
    this.onChange();
    void this.prefetch(appid);
  }

  /** Once a game has settled, its neighbours' links are looked up one at a time; no media is loaded. */
  private async prefetch(from: string): Promise<void> {
    for (const appid of this.neighbors()) {
      if (this.selected !== from) return;
      if (this.cache.has(appid) || this.prefetching.has(appid)) continue;
      this.prefetching.add(appid);
      try {
        this.cache.set(appid, await this.lookup(appid));
      } catch {
        /* a failed lookup is retried when the game is selected */
      } finally {
        this.prefetching.delete(appid);
      }
    }
  }
}

/** The soundtrack preview, faded in over whatever Ambiente was playing and faded out when left. */
export class ThemeAudio {
  private audio: HTMLAudioElement | null = null;
  private readonly fades = new Map<HTMLAudioElement, ReturnType<typeof setInterval>>();

  constructor(private readonly create: () => HTMLAudioElement | null) {}

  get url(): string | null {
    return this.audio?.getAttribute("src") ?? null;
  }

  play(url: string, volume: number): void {
    if (this.url === url) return;
    if (this.audio) this.silence(this.audio);
    const audio = this.create();
    if (!audio) return;
    audio.src = url;
    audio.loop = true;
    audio.volume = 0;
    this.audio = audio;
    void audio.play().catch(() => undefined);
    this.ramp(audio, Math.max(0, Math.min(1, volume)));
  }

  stop(): void {
    const audio = this.audio;
    this.audio = null;
    if (audio) this.ramp(audio, 0, () => this.silence(audio));
  }

  private silence(audio: HTMLAudioElement): void {
    const fade = this.fades.get(audio);
    if (fade !== undefined) clearInterval(fade);
    this.fades.delete(audio);
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
  }

  private ramp(audio: HTMLAudioElement, target: number, then?: () => void): void {
    const running = this.fades.get(audio);
    if (running !== undefined) clearInterval(running);
    const fade = setInterval(() => {
      const gap = target - audio.volume;
      audio.volume = Math.abs(gap) <= FADE_STEP ? target : audio.volume + Math.sign(gap) * FADE_STEP;
      if (audio.volume !== target) return;
      clearInterval(fade);
      this.fades.delete(audio);
      then?.();
    }, FADE_TICK_MS);
    this.fades.set(audio, fade);
  }
}

const FADE_STEP = 0.08;
const FADE_TICK_MS = 60;
