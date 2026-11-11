/** How long the music may fall silent (track change, buffering, a radio retry) before themes hear it stopped. */
export const MUSIC_SILENCE_SETTLE_MS = 1500;

export interface AudibleSnapshot {
  status: string;
  volume: number;
}

/** Ambiente's music is audible only while its player reports real playback at a volume above zero. */
export function musicAudible(player: AudibleSnapshot): boolean {
  return player.status === "playing" && player.volume > 0;
}

/**
 * Whether Ambiente's music is playing, for theme runtimes that fade their own music around it. Starting is
 * reported at once; stopping only after the silence lasts, so a gap between tracks does not make a theme flap.
 */
export class MusicActivity {
  private playing = false;
  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private readonly onChange: (playing: boolean) => void,
    private readonly settleMs = MUSIC_SILENCE_SETTLE_MS,
  ) {}

  update(audible: boolean): void {
    if (audible) {
      this.clear();
      if (!this.playing) this.set(true);
      return;
    }
    if (!this.playing || this.timer !== null) return;
    this.timer = setTimeout(() => {
      this.timer = null;
      this.set(false);
    }, this.settleMs);
  }

  dispose(): void {
    this.clear();
  }

  private set(playing: boolean): void {
    this.playing = playing;
    this.onChange(playing);
  }

  private clear(): void {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
  }
}
