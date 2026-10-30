interface AudioLoaderWindow {
  AUDIOLOADER_MENUMUSIC?: HTMLAudioElement | null;
}

/** Audio Loader keeps its menu music on a window global; Game Theme Music pauses it the same way. */
export class AudioLoaderBridge {
  private pausedByUs = false;

  constructor(private readonly win: AudioLoaderWindow = globalThis as unknown as AudioLoaderWindow) {}

  private element(): HTMLAudioElement | null {
    const music = this.win.AUDIOLOADER_MENUMUSIC;
    return music && typeof music.pause === "function" ? music : null;
  }

  isActive(): boolean {
    const music = this.element();
    return !!music && (!music.paused || this.pausedByUs);
  }

  yieldToPanel(): void {
    const music = this.element();
    if (music && !music.paused) {
      music.pause();
      this.pausedByUs = true;
    }
  }

  restore(): void {
    const music = this.element();
    if (music && this.pausedByUs) void music.play().catch(() => undefined);
    this.pausedByUs = false;
  }
}
