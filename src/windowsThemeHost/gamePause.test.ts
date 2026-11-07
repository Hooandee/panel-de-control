import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { GAME_PAUSE_BINDING, GAME_PAUSE_MAX_MS, installHostGamePause } from "./gamePause";

const steam = globalThis as { SteamUIStore?: { MainRunningAppID?: unknown } };

describe("host game pause", () => {
  beforeEach(() => {
    steam.SteamUIStore = { MainRunningAppID: 3564860 };
  });
  afterEach(() => {
    delete steam.SteamUIStore;
  });

  it("holds the running game for the lease, capped, and signals only when the lease starts or ends", async () => {
    let now = 1000;
    const signals: string[] = [];
    const scope = { [GAME_PAUSE_BINDING]: (payload: string) => { signals.push(payload); } } as unknown as typeof globalThis;
    const pause = installHostGamePause(scope, () => now);

    expect(await pause.games.pause(60_000)).toBe(true);
    expect(pause.paused()).toBe("3564860");
    now += GAME_PAUSE_MAX_MS - 1;
    expect(pause.paused()).toBe("3564860");
    now += 1;
    expect(pause.paused()).toBeNull();

    // A renewal while held only moves the deadline.
    await pause.games.pause(2500);
    await pause.games.pause(2500);
    expect(signals).toHaveLength(2);
    await pause.games.resume();
    expect(pause.paused()).toBeNull();
    expect(JSON.parse(signals[signals.length - 1])).toEqual({ appid: null, until: 0 });
  });

  it("does not pause without a running game, and gives the game back on dispose", async () => {
    const pause = installHostGamePause({} as typeof globalThis);
    delete steam.SteamUIStore;
    expect(await pause.games.pause(2500)).toBe(false);
    steam.SteamUIStore = { MainRunningAppID: 570 };
    expect(await pause.games.pause(2500)).toBe(true);
    pause.dispose();
    expect(pause.paused()).toBeNull();
  });

  it("offers no force close, which stays Steam's on Windows", () => {
    const pause = installHostGamePause({} as typeof globalThis);
    expect("forceClose" in pause.games).toBe(false);
  });
});
