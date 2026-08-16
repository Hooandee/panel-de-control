// @vitest-environment happy-dom
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const gameState = vi.hoisted(() => ({
  current: null as { appid: string; liveAppid: number; name: string } | null,
}));

vi.mock("./runningGame", () => ({
  readRunningGame: () => gameState.current,
}));

import { useRunningGame } from "./useRunningGame";

describe("useRunningGame", () => {
  let notifyLifetime: () => void;

  beforeEach(() => {
    vi.useFakeTimers();
    notifyLifetime = () => undefined;
    vi.stubGlobal("SteamClient", {
      GameSessions: {
        RegisterForAppLifetimeNotifications: (callback: () => void) => {
          notifyLifetime = callback;
          return { unregister: vi.fn() };
        },
      },
    });
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("recovers when Steam announces exit before MainRunningApp clears", async () => {
    gameState.current = { appid: "101", liveAppid: 101, name: "Game A" };
    const { result, unmount } = renderHook(() => useRunningGame());
    expect(result.current).toEqual(gameState.current);

    act(() => notifyLifetime());
    gameState.current = null;
    await act(async () => vi.advanceTimersByTimeAsync(2000));

    expect(result.current).toBeNull();
    unmount();
  });

  it("keeps the same snapshot through duplicate events and polls", async () => {
    gameState.current = { appid: "101", liveAppid: 101, name: "Game A" };
    const { result, unmount } = renderHook(() => useRunningGame());
    const initial = result.current;

    act(() => notifyLifetime());
    await act(async () => vi.advanceTimersByTimeAsync(4000));

    expect(result.current).toBe(initial);
    unmount();
  });
});
