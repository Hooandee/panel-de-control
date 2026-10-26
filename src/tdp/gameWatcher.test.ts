import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const performance = vi.hoisted(() => ({
  profile: "global" as "global" | "game" | "unknown",
  notify: () => undefined as void,
  unsubscribe: vi.fn(),
  read: vi.fn(),
}));
vi.mock("../steam/performanceRuntime", () => ({
  readSteamPerformanceProfile: (appid: number | null) => {
    performance.read(appid);
    return performance.profile;
  },
  subscribeSteamPerformanceState: (notify: () => void) => {
    performance.notify = notify;
    return performance.unsubscribe;
  },
}));
const setCurrentGame = vi.hoisted(() => vi.fn());
const gameState = vi.hoisted(() => ({
  current: null as { appid: string; liveAppid: number; name: string } | null,
}));

vi.mock("../api", () => ({ setCurrentGame }));
vi.mock("./runningGame", () => ({
  readRunningGame: () => gameState.current,
}));

import { startGameWatcher } from "./gameWatcher";

const game = (appid: string, name: string) => ({
  appid,
  liveAppid: Number(appid),
  name,
});

const flushPromises = async (): Promise<void> => {
  await Promise.resolve();
  await Promise.resolve();
};

function deferred(): {
  promise: Promise<void>;
  resolve: () => void;
} {
  let resolve!: () => void;
  const promise = new Promise<void>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe("startGameWatcher", () => {
  let notifyLifetime: () => void;
  let unregisterLifetime: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.useFakeTimers();
    gameState.current = null;
    performance.profile = "global";
    performance.unsubscribe.mockClear();
    performance.read.mockClear();
    setCurrentGame.mockReset();
    setCurrentGame.mockResolvedValue(undefined);
    notifyLifetime = () => undefined;
    unregisterLifetime = vi.fn();
    vi.stubGlobal("SteamClient", {
      GameSessions: {
        RegisterForAppLifetimeNotifications: (callback: () => void) => {
          notifyLifetime = callback;
          return { unregister: unregisterLifetime };
        },
      },
    });
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("reports Steam profile changes for the same game through the persistent listener", async () => {
    gameState.current = { appid: "shortcut", liveAppid: 101, name: "Game A" };
    performance.profile = "game";
    const stop = startGameWatcher();
    await flushPromises();
    expect(performance.read).toHaveBeenCalledWith(101);
    performance.profile = "global";
    performance.notify();
    await flushPromises();
    expect(setCurrentGame.mock.calls).toEqual([
      ["shortcut", "Game A", "active"],
      ["shortcut", "Game A", "inactive"],
    ]);
    stop();
    performance.profile = "game";
    performance.notify();
    await flushPromises();
    expect(setCurrentGame).toHaveBeenCalledTimes(2);
  });

  it("polls unknown profile recovery without requiring an open panel", async () => {
    gameState.current = game("101", "Game A");
    performance.profile = "unknown";
    const stop = startGameWatcher();
    await flushPromises();
    performance.profile = "game";
    await vi.advanceTimersByTimeAsync(2000);
    expect(setCurrentGame.mock.calls).toEqual([
      ["101", "Game A", "unknown"],
      ["101", "Game A", "active"],
    ]);
    stop();
  });

  it("repairs a profile observation after an expired request completes late", async () => {
    const first = deferred();
    setCurrentGame.mockImplementationOnce(() => first.promise);
    gameState.current = game("101", "Game A");
    performance.profile = "game";
    const stop = startGameWatcher();
    performance.profile = "global";
    performance.notify();
    await vi.advanceTimersByTimeAsync(30000);
    first.resolve();
    await flushPromises();
    expect(setCurrentGame.mock.calls).toEqual([
      ["101", "Game A", "active"],
      ["101", "Game A", "inactive"],
      ["101", "Game A", "inactive"],
    ]);
    stop();
  });

  it("confirms startup idle after allowing Router to hydrate", async () => {
    const stop = startGameWatcher();
    await flushPromises();

    expect(setCurrentGame).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1999);
    expect(setCurrentGame).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(setCurrentGame.mock.calls).toEqual([[null, null, "inactive"]]);
    stop();
  });

  it("recovers when Steam announces exit before MainRunningApp clears", async () => {
    gameState.current = game("101", "Game A");
    const stop = startGameWatcher();
    await flushPromises();

    notifyLifetime();
    gameState.current = null;
    await vi.advanceTimersByTimeAsync(2000);

    expect(setCurrentGame.mock.calls).toEqual([
      ["101", "Game A", "inactive"],
      [null, null, "inactive"],
    ]);
    stop();
  });

  it("applies the latest observation after an older request resolves", async () => {
    const firstRequest = deferred();
    setCurrentGame.mockImplementationOnce(() => firstRequest.promise);
    gameState.current = game("101", "Game A");
    const stop = startGameWatcher();

    gameState.current = null;
    notifyLifetime();
    firstRequest.resolve();
    await flushPromises();

    expect(setCurrentGame.mock.calls).toEqual([
      ["101", "Game A", "inactive"],
      [null, null, "inactive"],
    ]);
    stop();
  });

  it("retries a failed exit report without another Steam event", async () => {
    gameState.current = game("101", "Game A");
    const stop = startGameWatcher();
    await flushPromises();

    gameState.current = null;
    setCurrentGame.mockRejectedValueOnce(new Error("RPC unavailable"));
    notifyLifetime();
    await flushPromises();
    await vi.advanceTimersByTimeAsync(2000);

    expect(setCurrentGame.mock.calls).toEqual([
      ["101", "Game A", "inactive"],
      [null, null, "inactive"],
      [null, null, "inactive"],
    ]);
    stop();
  });

  it("retries a synchronous transport failure on the next poll", async () => {
    gameState.current = game("101", "Game A");
    const stop = startGameWatcher();
    await flushPromises();

    gameState.current = null;
    setCurrentGame.mockImplementationOnce(() => {
      throw new Error("bridge unavailable");
    });
    notifyLifetime();
    await vi.advanceTimersByTimeAsync(2000);

    expect(setCurrentGame.mock.calls).toEqual([
      ["101", "Game A", "inactive"],
      [null, null, "inactive"],
      [null, null, "inactive"],
    ]);
    stop();
  });

  it("moves to the latest context when an older request never settles", async () => {
    const stalled = deferred();
    setCurrentGame.mockImplementationOnce(() => stalled.promise);
    gameState.current = game("101", "Game A");
    const stop = startGameWatcher();

    gameState.current = null;
    notifyLifetime();
    await vi.advanceTimersByTimeAsync(29999);
    expect(setCurrentGame.mock.calls).toEqual([["101", "Game A", "inactive"]]);
    await vi.advanceTimersByTimeAsync(1);

    expect(setCurrentGame.mock.calls).toEqual([
      ["101", "Game A", "inactive"],
      [null, null, "inactive"],
    ]);
    stop();
  });

  it("repairs the context when an expired request resolves late", async () => {
    const stalled = deferred();
    setCurrentGame.mockImplementationOnce(() => stalled.promise);
    gameState.current = game("101", "Game A");
    const stop = startGameWatcher();

    gameState.current = null;
    notifyLifetime();
    await vi.advanceTimersByTimeAsync(30000);
    await flushPromises();
    stalled.resolve();
    await flushPromises();

    expect(setCurrentGame.mock.calls).toEqual([
      ["101", "Game A", "inactive"],
      [null, null, "inactive"],
      [null, null, "inactive"],
    ]);
    stop();
  });

  it("bounds unresolved reports when the transport stays hung", async () => {
    setCurrentGame.mockImplementation(() => new Promise(() => undefined));
    gameState.current = game("101", "Game A");
    const stop = startGameWatcher();

    gameState.current = null;
    notifyLifetime();
    await vi.advanceTimersByTimeAsync(120000);

    expect(setCurrentGame.mock.calls).toEqual([
      ["101", "Game A", "inactive"],
      [null, null, "inactive"],
    ]);
    stop();
  });

  it("keeps polling when lifetime notifications are unavailable", async () => {
    vi.stubGlobal("SteamClient", undefined);
    const stop = startGameWatcher();
    await flushPromises();

    gameState.current = game("101", "Game A");
    await vi.advanceTimersByTimeAsync(2000);

    expect(setCurrentGame.mock.calls).toEqual([["101", "Game A", "inactive"]]);
    stop();
  });

  it("keeps polling when lifetime notification registration throws", async () => {
    vi.stubGlobal("SteamClient", {
      GameSessions: {
        RegisterForAppLifetimeNotifications: () => {
          throw new Error("unsupported Steam API");
        },
      },
    });
    const stop = startGameWatcher();
    await flushPromises();

    gameState.current = game("101", "Game A");
    await vi.advanceTimersByTimeAsync(2000);

    expect(setCurrentGame.mock.calls).toEqual([["101", "Game A", "inactive"]]);
    stop();
  });

  it("deduplicates notification bursts and steady polls", async () => {
    gameState.current = game("101", "Game A");
    const stop = startGameWatcher();
    await flushPromises();

    notifyLifetime();
    notifyLifetime();
    await vi.advanceTimersByTimeAsync(6000);

    expect(setCurrentGame.mock.calls).toEqual([["101", "Game A", "inactive"]]);
    stop();
  });

  it("drops queued observations when the watcher stops", async () => {
    const request = deferred();
    setCurrentGame.mockImplementationOnce(() => request.promise);
    gameState.current = game("101", "Game A");
    const stop = startGameWatcher();

    gameState.current = null;
    notifyLifetime();
    stop();
    request.resolve();
    await flushPromises();
    await vi.advanceTimersByTimeAsync(2000);

    expect(setCurrentGame.mock.calls).toEqual([["101", "Game A", "inactive"]]);
    expect(unregisterLifetime).toHaveBeenCalledOnce();
    expect(performance.unsubscribe).toHaveBeenCalledOnce();
  });
});
