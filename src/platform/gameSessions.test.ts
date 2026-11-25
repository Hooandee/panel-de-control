import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({ Router: {} }));

import { createGameSessionPort } from "./gameSessions";

describe("game session port", () => {
  afterEach(() => {
    vi.useRealTimers();
    delete (globalThis as { SteamClient?: unknown }).SteamClient;
  });

  it("notifies once per game change after a lifetime event", () => {
    vi.useFakeTimers();
    let handler: (() => void) | undefined;
    const unregister = vi.fn();
    (globalThis as { SteamClient?: unknown }).SteamClient = {
      GameSessions: { RegisterForAppLifetimeNotifications: (cb: () => void) => { handler = cb; return { unregister }; } },
    };
    let game: { appid: string; liveAppid: number; name: string } | null = null;
    const seen: (string | null)[] = [];
    const stop = createGameSessionPort(() => game).subscribe((g) => seen.push(g?.appid ?? null));
    game = { appid: "730", liveAppid: 730, name: "CS2" };
    handler?.();
    handler?.();
    vi.advanceTimersByTime(500);
    game = null;
    handler?.();
    vi.advanceTimersByTime(500);
    expect(seen).toEqual(["730", null]);
    stop();
    expect(unregister).toHaveBeenCalled();
  });

  it("falls back to polling without Steam events", () => {
    vi.useFakeTimers();
    let game: { appid: string; liveAppid: number; name: string } | null = null;
    const seen: (string | null)[] = [];
    const stop = createGameSessionPort(() => game).subscribe((g) => seen.push(g?.appid ?? null));
    game = { appid: "1", liveAppid: 1, name: "x" };
    vi.advanceTimersByTime(5000);
    expect(seen).toEqual(["1"]);
    stop();
  });
});
