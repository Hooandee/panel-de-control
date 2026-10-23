// Steam on Windows has no per-app audio service (SteamClient.System.Audio), so a theme that silences the running
// game while Steam is in front asks the host, and the companion mutes the game's sessions in the Windows mixer.
export const HOST_GAME_AUDIO_KEY = "__pdcHostGameAudio";
/** CDP binding the companion adds to SharedJSContext; calling it reaches the companion at once. */
export const GAME_AUDIO_BINDING = "pdcHostGameAudio";

export interface HostGameAudio {
  setGameSilenced(silenced: boolean): void;
}

type AudioScope = typeof globalThis & {
  [HOST_GAME_AUDIO_KEY]?: HostGameAudio;
  [GAME_AUDIO_BINDING]?: (payload: string) => void;
};

export function installHostGameAudio(scope: typeof globalThis): { silenced(): boolean; dispose(): void } {
  const target = scope as AudioScope;
  let silenced = false;
  const signal = () => {
    try {
      target[GAME_AUDIO_BINDING]?.(JSON.stringify({ silenced }));
    } catch {
      // Without the binding the companion still reads the state from the host's status.
    }
  };
  const audio: HostGameAudio = Object.freeze({
    setGameSilenced(next: boolean) {
      if (next === silenced) return;
      silenced = next;
      signal();
    },
  });
  target[HOST_GAME_AUDIO_KEY] = audio;
  return {
    silenced: () => silenced,
    dispose() {
      if (target[HOST_GAME_AUDIO_KEY] === audio) delete target[HOST_GAME_AUDIO_KEY];
      if (silenced) {
        silenced = false;
        signal();
      }
    },
  };
}
