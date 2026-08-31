// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";

import { startSteamSurfaceSession } from "./surfaceSession";

interface FakeObserver {
  callback: MutationCallback;
  observe: ReturnType<typeof vi.fn>;
  disconnect: ReturnType<typeof vi.fn>;
}

describe("startSteamSurfaceSession", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("observes only Steam's active main surface and its direct replacement boundary", () => {
    document.body.innerHTML = '<div id="shell"><main id="Main"><div role="listitem" data-id="GoToLibrary"></div></main></div>';
    const observers: FakeObserver[] = [];
    const onSurface = vi.fn();
    const stop = startSteamSurfaceSession({
      doc: document,
      onSurface,
      createObserver: (callback) => {
        const observer = { callback, observe: vi.fn(), disconnect: vi.fn() };
        observers.push(observer);
        return observer;
      },
      requestAnimationFrame: vi.fn(() => 1),
      cancelAnimationFrame: vi.fn(),
    });

    const main = document.getElementById("Main");
    const shell = document.getElementById("shell");
    expect(observers).toHaveLength(2);
    expect(observers[0].observe).toHaveBeenCalledWith(main, { childList: true, subtree: true });
    expect(observers[1].observe).toHaveBeenCalledWith(shell, { childList: true });
    expect(onSurface).toHaveBeenCalledWith("library", main);

    stop();
    expect(observers.every((observer) => observer.disconnect.mock.calls.length === 1)).toBe(true);
  });

  it("coalesces mutations and rebinds when Steam replaces Main", () => {
    document.body.innerHTML = '<div id="shell"><main id="Main"></main></div>';
    const observers: FakeObserver[] = [];
    let scheduled: FrameRequestCallback | undefined;
    const requestAnimationFrame = vi.fn((callback: FrameRequestCallback) => {
      scheduled = callback;
      return 4;
    });
    const stop = startSteamSurfaceSession({
      doc: document,
      onSurface: vi.fn(),
      createObserver: (callback) => {
        const observer = { callback, observe: vi.fn(), disconnect: vi.fn() };
        observers.push(observer);
        return observer;
      },
      requestAnimationFrame,
      cancelAnimationFrame: vi.fn(),
    });

    observers[0].callback([], observers[0] as unknown as MutationObserver);
    observers[1].callback([], observers[1] as unknown as MutationObserver);
    expect(requestAnimationFrame).toHaveBeenCalledOnce();

    document.getElementById("Main")?.replaceWith(Object.assign(document.createElement("main"), { id: "Main" }));
    scheduled?.(0);
    expect(observers).toHaveLength(4);
    expect(observers[2].observe).toHaveBeenCalledWith(document.getElementById("Main"), { childList: true, subtree: true });
    expect(observers[0].disconnect).toHaveBeenCalledOnce();
    expect(observers[1].disconnect).toHaveBeenCalledOnce();

    stop();
  });

  it("exposes route mutations before deferring full surface detection", () => {
    document.body.innerHTML = '<div id="shell"><main id="Main"><div role="listitem" data-id="GoToLibrary"></div></main></div>';
    const observers: FakeObserver[] = [];
    const onBeforeRefresh = vi.fn();
    const requestAnimationFrame = vi.fn(() => 5);
    const stop = startSteamSurfaceSession({
      doc: document,
      onSurface: vi.fn(),
      onBeforeRefresh,
      createObserver: (callback) => {
        const observer = { callback, observe: vi.fn(), disconnect: vi.fn() };
        observers.push(observer);
        return observer;
      },
      requestAnimationFrame,
      cancelAnimationFrame: vi.fn(),
    });
    const record = { addedNodes: [], removedNodes: [] } as unknown as MutationRecord;

    observers[0].callback([record], observers[0] as unknown as MutationObserver);

    expect(onBeforeRefresh).toHaveBeenCalledWith([record]);
    expect(requestAnimationFrame).toHaveBeenCalledOnce();
    stop();
    observers[0].callback([record], observers[0] as unknown as MutationObserver);
    expect(onBeforeRefresh).toHaveBeenCalledOnce();
    expect(requestAnimationFrame).toHaveBeenCalledOnce();
  });

  it("keeps surface detection alive when the immediate mutation hook fails", () => {
    document.body.innerHTML = '<div id="shell"><main id="Main"></main></div>';
    const observers: FakeObserver[] = [];
    const requestAnimationFrame = vi.fn(() => 6);
    const stop = startSteamSurfaceSession({
      doc: document,
      onSurface: vi.fn(),
      onBeforeRefresh: () => { throw new Error("hook failed"); },
      createObserver: (callback) => {
        const observer = { callback, observe: vi.fn(), disconnect: vi.fn() };
        observers.push(observer);
        return observer;
      },
      requestAnimationFrame,
      cancelAnimationFrame: vi.fn(),
    });

    expect(() => observers[0].callback([], observers[0] as unknown as MutationObserver))
      .not.toThrow();
    expect(requestAnimationFrame).toHaveBeenCalledOnce();
    stop();
  });

  it("uses a temporary discovery observer until Steam creates Main", () => {
    const observers: FakeObserver[] = [];
    let scheduled: FrameRequestCallback | undefined;
    const onSurface = vi.fn();
    const stop = startSteamSurfaceSession({
      doc: document,
      onSurface,
      createObserver: (callback) => {
        const observer = { callback, observe: vi.fn(), disconnect: vi.fn() };
        observers.push(observer);
        return observer;
      },
      requestAnimationFrame: (callback) => {
        scheduled = callback;
        return 9;
      },
      cancelAnimationFrame: vi.fn(),
    });

    expect(observers).toHaveLength(1);
    expect(observers[0].observe).toHaveBeenCalledWith(document.body, { childList: true, subtree: true });

    document.body.innerHTML = '<main id="Main"><div role="listitem" data-id="GoToLibrary"></div></main>';
    observers[0].callback([], observers[0] as unknown as MutationObserver);
    scheduled?.(0);
    expect(observers[0].disconnect).toHaveBeenCalledOnce();
    expect(observers[1].observe).toHaveBeenCalledWith(document.getElementById("Main"), { childList: true, subtree: true });
    expect(onSurface).toHaveBeenLastCalledWith("library", document.getElementById("Main"));

    stop();
  });

  it("holds the chosen surface while Steam keeps both route trees mounted", () => {
    document.body.innerHTML = '<div id="shell"><main id="Main"><div role="listitem" data-id="GoToLibrary"></div></main></div>';
    const observers: FakeObserver[] = [];
    const onSurface = vi.fn();
    let scheduled: FrameRequestCallback | undefined;
    const stop = startSteamSurfaceSession({
      doc: document,
      onSurface,
      createObserver: (callback) => {
        const observer = { callback, observe: vi.fn(), disconnect: vi.fn() };
        observers.push(observer);
        return observer;
      },
      requestAnimationFrame(callback) {
        scheduled = callback;
        return 1;
      },
      cancelAnimationFrame: vi.fn(),
    });
    const main = document.getElementById("Main")!;
    const refresh = () => {
      const mainObserver = observers[observers.length - 2];
      mainObserver?.callback([], mainObserver as unknown as MutationObserver);
      scheduled?.(0);
    };

    main.insertAdjacentHTML("beforeend", '<div role="tab" aria-controls="Tabs_GameInfo_Content"></div>');
    refresh();
    expect(onSurface).toHaveBeenLastCalledWith("game-details", main);
    refresh();
    expect(onSurface).toHaveBeenLastCalledWith("game-details", main);

    main.querySelector('[data-id="GoToLibrary"]')?.remove();
    refresh();
    expect(onSurface).toHaveBeenLastCalledWith("game-details", main);

    main.insertAdjacentHTML("beforeend", '<div role="listitem" data-id="GoToLibrary"></div>');
    refresh();
    expect(onSurface).toHaveBeenLastCalledWith("library", main);
    refresh();
    expect(onSurface).toHaveBeenLastCalledWith("library", main);

    main.querySelector('[aria-controls$="GameInfo_Content"]')?.remove();
    refresh();
    expect(onSurface).toHaveBeenLastCalledWith("library", main);
    stop();
  });

  it("disconnects observers already attached when a later setup step fails", () => {
    document.body.innerHTML = '<div id="shell"><main id="Main"></main></div>';
    const observers: FakeObserver[] = [];

    expect(() => startSteamSurfaceSession({
      doc: document,
      onSurface: vi.fn(),
      createObserver: (callback) => {
        const index = observers.length;
        const observer = {
          callback,
          observe: vi.fn(() => {
            if (index === 1) throw new Error("boundary rejected");
          }),
          disconnect: vi.fn(),
        };
        observers.push(observer);
        return observer;
      },
      requestAnimationFrame: vi.fn(() => 1),
      cancelAnimationFrame: vi.fn(),
    })).toThrow("boundary rejected");

    expect(observers[0].disconnect).toHaveBeenCalledOnce();
    expect(observers[1].disconnect).toHaveBeenCalledOnce();
  });
});
