import { describe, expect, it } from "vitest";

import { GAME_AUDIO_BINDING, HOST_GAME_AUDIO_KEY, installHostGameAudio, type HostGameAudio } from "./gameAudio";

describe("host game audio", () => {
  it("signals each change through the companion's binding and gives the sound back on dispose", () => {
    const signals: string[] = [];
    const scope = { [GAME_AUDIO_BINDING]: (payload: string) => { signals.push(payload); } } as unknown as typeof globalThis;
    const installed = installHostGameAudio(scope);
    const audio = (scope as unknown as Record<string, HostGameAudio>)[HOST_GAME_AUDIO_KEY];

    audio.setGameSilenced(true);
    audio.setGameSilenced(true);
    expect(installed.silenced()).toBe(true);
    audio.setGameSilenced(false);
    audio.setGameSilenced(true);
    installed.dispose();

    expect(signals).toEqual(['{"silenced":true}', '{"silenced":false}', '{"silenced":true}', '{"silenced":false}']);
    expect(HOST_GAME_AUDIO_KEY in scope).toBe(false);
  });

  it("keeps working without the binding", () => {
    const scope = {} as typeof globalThis;
    const installed = installHostGameAudio(scope);
    (scope as unknown as Record<string, HostGameAudio>)[HOST_GAME_AUDIO_KEY].setGameSilenced(true);
    expect(installed.silenced()).toBe(true);
    installed.dispose();
  });
});
