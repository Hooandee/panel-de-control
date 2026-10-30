// @vitest-environment happy-dom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useEffect, type CSSProperties, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import defaults from "../../../shared/contracts/ambient/fixtures/defaults.json";
import type { AmbientSettings } from "../core/types";
import type { AmbientRuntime, AmbientSnapshot } from "../steam/runtime";
import { FloatingPlayer } from "./FloatingPlayer";
import { registerLibraryDock, setLibraryDockFocus } from "./libraryDock";
import { setAmbientRuntime } from "./useAmbient";

const platform = vi.hoisted(() => ({
  composition: null as number | null,
  capture: null as ((button: number) => void) | null,
  trees: [] as Array<{ id?: string; m_ID?: string; m_Root?: { m_element: HTMLElement }; Root?: { Element: HTMLElement } }>,
}));

vi.mock("@decky/ui", () => ({
  findSP: () => window,
  getGamepadNavigationTrees: () => platform.trees,
  Focusable: ({ children, style, onClick, "aria-label": label }: { children?: ReactNode; style?: CSSProperties; onClick?: () => void; "aria-label"?: string }) => <div style={style} onClick={onClick} aria-label={label}>{children}</div>,
  SliderField: () => null,
}));
vi.mock("../../i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }));
vi.mock("../../platform/qamSurface", () => ({ subscribeQamSurface: () => () => undefined, onQamLeftEdge: () => () => undefined, qamPanelWidth: () => 0 }));
vi.mock("../../platform/buttonCapture", () => ({
  captureButtons: (_buttons: readonly number[], callback: (button: number) => void) => {
    platform.capture = callback;
    return () => { platform.capture = null; };
  },
}));
vi.mock("../../platform/overGameComposition", () => ({
  UIComposition: { Notification: 1, Overlay: 2 },
  canDrawOverGames: () => true,
  OverGameComposition: ({ level }: { level: number }) => {
    useEffect(() => {
      platform.composition = level;
      return () => { platform.composition = null; };
    }, [level]);
    return null;
  },
}));

function runtimeStore(inGame = true) {
  let snapshot: AmbientSnapshot = {
    ready: true,
    state: { settings: structuredClone(defaults) as AmbientSettings, knownFolders: { images: [], videos: [], music: [] }, collections: [], mediaServer: "loopback" },
    scan: null,
    items: [],
    previews: {},
    current: null,
    currentUrl: null,
    previewUrl: null,
    decision: { background: "panel", music: "panel", conflict: null },
    motion: "play",
    surface: "home",
    optimizing: false,
    suggestedStations: [],
    selectedGame: null,
    coveredBy: [],
    pageOpen: false,
    libraryOpen: false,
    libraryShown: false,
    floatingMissing: false,
    error: null,
    inGame,
    overlayControl: false,
    videoFullscreen: false,
    videoCollapsed: false,
    player: { status: "playing", video: true, picture: true, position: 42, duration: 300, volume: 0.6, error: null, queue: [], queueIndex: 0, repeat: "all", shuffle: false, track: { id: "video", title: "Example video", subtitle: "", art: "", url: "https://example.test/video.mp4", live: false, kind: "video" } },
  };
  const listeners = new Set<() => void>();
  let previousControl = false;
  const publish = (patch: Partial<AmbientSnapshot>) => {
    snapshot = { ...snapshot, ...patch };
    for (const listener of listeners) listener();
  };
  const runtime = {
    getSnapshot: () => snapshot,
    subscribe: (listener: () => void) => { listeners.add(listener); return () => listeners.delete(listener); },
    setVideoBounds: vi.fn(),
    setVideoVisible: vi.fn(),
    markFloatingMounted: vi.fn(() => () => undefined),
    isFavoriteTrack: () => false,
    canFavoriteTrack: () => false,
    canShowVideo: () => snapshot.player.video,
    pauseMusic: vi.fn(),
    resumeMusic: vi.fn(),
    nextTrack: vi.fn(),
    previousTrack: vi.fn(),
    seekFraction: vi.fn(),
    seekBy: vi.fn(),
    setVolume: vi.fn(),
    updateSettings: vi.fn(),
    toggleVideo: vi.fn(),
    startOverlayControl: vi.fn(() => publish({ overlayControl: true })),
    stopOverlayControl: vi.fn(() => publish({ overlayControl: false, videoFullscreen: false })),
    setVideoFullscreen: vi.fn((on: boolean) => {
      if (on) previousControl = snapshot.overlayControl;
      publish({ videoFullscreen: on, overlayControl: on || previousControl });
    }),
  };
  setAmbientRuntime(runtime as unknown as AmbientRuntime);
  return { runtime, publish, snapshot: () => snapshot };
}

function fullscreenButton() {
  return screen.getByRole("button", { name: "ambient.player.fullscreen" });
}

function controlsOf(button: HTMLElement): HTMLElement {
  let node: HTMLElement | null = button;
  while (node && !node.style.transition.includes("opacity")) node = node.parentElement;
  if (!node) throw new Error("Video controls are missing");
  return node;
}

describe("FloatingPlayer fullscreen", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(100000);
    vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockReturnValue(288);
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
    platform.composition = null;
    platform.capture = null;
    platform.trees = [];
  });

  afterEach(() => {
    cleanup();
    setAmbientRuntime(null);
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("fades controls after three seconds but keeps the game's controller beyond the floating idle timeout", async () => {
    const store = runtimeStore();
    render(<FloatingPlayer />);
    fireEvent.click(fullscreenButton());
    const controls = controlsOf(screen.getByRole("button", { name: "ambient.player.exitFullscreen" }));
    expect(controls.style.opacity).toBe("1");
    await act(async () => { await vi.advanceTimersByTimeAsync(3100); });
    expect(controls.style.opacity).toBe("0");
    expect(controls.style.pointerEvents).toBe("none");
    await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
    expect(platform.composition).toBe(2);
    expect(store.runtime.stopOverlayControl).not.toHaveBeenCalled();
    expect(store.snapshot().videoFullscreen).toBe(true);
    expect(store.runtime.setVideoBounds).toHaveBeenLastCalledWith(expect.objectContaining({ x: 0, width: window.innerWidth, radius: 0 }));
  });

  it("the ← that enters control mode does not also move the card, later ones do", () => {
    const store = runtimeStore(false);
    render(<FloatingPlayer />);
    act(() => store.publish({ overlayControl: true }));
    const settings = () => store.runtime.updateSettings.mock.calls.length;
    const before = settings();
    act(() => { platform.capture!(11); });
    expect(settings()).toBe(before);
    act(() => { vi.advanceTimersByTime(500); });
    act(() => { platform.capture!(11); });
    act(() => { vi.advanceTimersByTime(600); });
    expect(settings()).toBeGreaterThan(before);
  });

  it("in a game the controller reaches the card in control mode, with Steam keeping the game's input", () => {
    const store = runtimeStore(true);
    render(<FloatingPlayer />);
    expect(platform.capture).toBeNull();
    act(() => store.publish({ overlayControl: true }));
    expect(platform.composition).toBe(2);
    expect(platform.capture).not.toBeNull();
    act(() => { platform.capture!(1); });
    expect(store.runtime.pauseMusic).toHaveBeenCalledOnce();
    act(() => { platform.capture!(2); });
    expect(store.runtime.stopOverlayControl).toHaveBeenCalled();
    expect(platform.capture).toBeNull();
  });

  it("B restores floating geometry without changing playback", async () => {
    const store = runtimeStore(false);
    render(<FloatingPlayer />);
    const calls = store.runtime.setVideoBounds.mock.calls;
    const floating = calls[calls.length - 1]?.[0];
    expect(floating).toBeDefined();
    fireEvent.click(fullscreenButton());
    expect(platform.capture).not.toBeNull();
    act(() => { platform.capture!(2); });
    await act(async () => { await vi.advanceTimersByTimeAsync(20); });
    expect(store.snapshot().videoFullscreen).toBe(false);
    expect(store.runtime.setVideoBounds).toHaveBeenLastCalledWith(floating);
    expect(platform.capture).toBeNull();
    expect(store.runtime.pauseMusic).not.toHaveBeenCalled();
    expect(store.runtime.resumeMusic).not.toHaveBeenCalled();
    expect(store.runtime.seekFraction).not.toHaveBeenCalled();
    expect(store.snapshot().player.position).toBe(42);
    expect(store.snapshot().player.volume).toBe(0.6);
  });

  it("reveals docked video only while a library control owns focus and releases the focused dock", () => {
    const store = runtimeStore(false);
    render(<FloatingPlayer />);
    const button = screen.getByRole("button", { name: "ambient.player.pause" });
    const controls = controlsOf(button);
    const anchor = document.createElement("div");
    document.body.appendChild(anchor);
    let release!: () => void;
    act(() => {
      release = registerLibraryDock({ runtime: store.runtime as unknown as AmbientRuntime, element: anchor });
      store.publish({ libraryOpen: true });
    });
    expect(controls.style.opacity).toBe("0");
    act(() => setLibraryDockFocus(anchor, "toggle"));
    expect(controls.style.opacity).toBe("1");
    act(() => setLibraryDockFocus(anchor, "progress"));
    expect(controls.style.opacity).toBe("1");
    act(() => setLibraryDockFocus(anchor, null, "toggle"));
    expect(controls.style.opacity).toBe("1");
    act(() => setLibraryDockFocus(anchor, null, "progress"));
    expect(controls.style.opacity).toBe("0");
    act(() => { setLibraryDockFocus(anchor, "toggle"); release(); });
    expect(store.runtime.setVideoVisible).toHaveBeenLastCalledWith(false);
    anchor.remove();
  });

  it("moves the same card into the library and back, including fullscreen, without restarting playback", () => {
    const store = runtimeStore(false);
    render(<FloatingPlayer />);
    const original = screen.getByRole("button", { name: "ambient.player.pause" });
    const host = document.getElementById("pdc-ambient-floating")!;
    const anchor = document.createElement("div");
    document.body.appendChild(anchor);
    vi.spyOn(anchor, "getBoundingClientRect").mockReturnValue({ x: 500, y: 190, width: 200, height: 113 } as DOMRect);
    let release!: () => void;
    act(() => {
      release = registerLibraryDock({ runtime: store.runtime as unknown as AmbientRuntime, element: anchor });
      store.publish({ libraryOpen: true });
    });
    expect(host.parentElement).toBe(document.body);
    expect(host.firstElementChild).toHaveProperty("style.left", "500px");
    expect(screen.getByRole("button", { name: "ambient.player.pause" })).toBe(original);
    expect(platform.capture).toBeNull();
    expect(store.runtime.setVideoBounds).toHaveBeenLastCalledWith({ x: 500, y: 190, width: 200, height: 113 });
    expect(store.runtime.setVideoVisible).toHaveBeenLastCalledWith(true);
    expect(screen.queryByRole("button", { name: "ambient.player.fullscreen" })).toBeNull();
    expect(screen.queryByRole("button", { name: "ambient.player.hideVideo" })).toBeNull();
    expect(screen.queryByRole("button", { name: "ambient.player.next" })).toBeNull();
    act(() => store.runtime.setVideoFullscreen(true));
    expect(host.parentElement).toBe(document.body);
    expect(platform.capture).toBeNull();
    expect(store.snapshot().libraryOpen).toBe(true);
    act(() => store.runtime.setVideoFullscreen(false));
    expect(store.snapshot().libraryOpen).toBe(true);
    expect(host.parentElement).toBe(document.body);
    expect(host.firstElementChild).toHaveProperty("style.left", "500px");
    expect(screen.getByRole("button", { name: "ambient.player.pause" })).toBe(original);
    expect(platform.capture).toBeNull();
    act(() => { release(); store.publish({ libraryOpen: false }); });
    expect(host.parentElement).toBe(document.body);
    expect(screen.getByRole("button", { name: "ambient.player.pause" })).toBe(original);
    expect(fullscreenButton()).toBeTruthy();
    expect(screen.getByRole("button", { name: "ambient.player.hideVideo" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "ambient.player.next" })).toBeTruthy();
    expect(store.runtime.pauseMusic).not.toHaveBeenCalled();
    expect(store.runtime.resumeMusic).not.toHaveBeenCalled();
    expect(store.snapshot().player.position).toBe(42);
    anchor.remove();
  });

  it("a removed track releases composition and removes the fullscreen player", () => {
    const store = runtimeStore();
    render(<FloatingPlayer />);
    fireEvent.click(fullscreenButton());
    act(() => store.publish({ player: { ...store.snapshot().player, track: null, status: "idle", video: false } }));
    expect(store.runtime.stopOverlayControl).toHaveBeenCalledOnce();
    expect(platform.composition).toBeNull();
    expect(store.runtime.setVideoVisible).toHaveBeenLastCalledWith(false);
    expect(screen.queryByRole("button", { name: "ambient.player.exitFullscreen" })).toBeNull();
  });

  it("a paused video stops covering the screen once its peek is over", () => {
    const store = runtimeStore();
    render(<FloatingPlayer />);
    act(() => store.publish({ player: { ...store.snapshot().player, status: "paused" } }));
    act(() => { vi.advanceTimersByTime(10000); });
    expect(store.runtime.setVideoVisible).toHaveBeenLastCalledWith(false);
    act(() => store.publish({ player: { ...store.snapshot().player, status: "playing" } }));
    expect(store.runtime.setVideoVisible).toHaveBeenLastCalledWith(true);
  });

  it("keeps the video out of the way on library tabs that have no slot for it, without stopping the sound", () => {
    const store = runtimeStore(false);
    render(<FloatingPlayer />);
    expect(store.runtime.setVideoVisible).toHaveBeenLastCalledWith(true);
    act(() => store.publish({ libraryShown: true }));
    expect(store.runtime.setVideoVisible).toHaveBeenLastCalledWith(false);
    expect(store.runtime.pauseMusic).not.toHaveBeenCalled();
    act(() => store.publish({ libraryShown: false }));
    expect(store.runtime.setVideoVisible).toHaveBeenLastCalledWith(true);
  });

  it("a stream with sound only hides the empty video area while it keeps playing", () => {
    const store = runtimeStore();
    render(<FloatingPlayer />);
    expect(store.runtime.setVideoVisible).toHaveBeenLastCalledWith(true);
    act(() => store.publish({ player: { ...store.snapshot().player, picture: false } }));
    expect(store.runtime.setVideoVisible).toHaveBeenLastCalledWith(false);
    expect(store.runtime.pauseMusic).not.toHaveBeenCalled();
  });

  it("a transition to audio hides the video and returns composition to notifications", () => {
    const store = runtimeStore();
    render(<FloatingPlayer />);
    fireEvent.click(fullscreenButton());
    act(() => store.publish({
      player: { ...store.snapshot().player, video: false, track: { ...store.snapshot().player.track!, kind: "audio", title: "Example audio" } },
      videoFullscreen: false,
      overlayControl: false,
    }));
    expect(screen.queryByRole("button", { name: "ambient.player.exitFullscreen" })).toBeNull();
    expect(store.runtime.setVideoVisible).toHaveBeenLastCalledWith(false);
    expect(platform.composition).toBe(1);
    expect(store.runtime.pauseMusic).not.toHaveBeenCalled();
  });

  it("releases controller capture on unmount and reacquires it for a still-playing fullscreen session", () => {
    const store = runtimeStore(false);
    const first = render(<FloatingPlayer />);
    fireEvent.click(fullscreenButton());
    expect(platform.capture).not.toBeNull();
    first.unmount();
    expect(platform.capture).toBeNull();
    expect(document.getElementById("pdc-ambient-floating")).toBeNull();
    render(<FloatingPlayer />);
    expect(platform.capture).not.toBeNull();
    expect(screen.getByRole("button", { name: "ambient.player.exitFullscreen" })).toBeTruthy();
    act(() => { platform.capture!(2); });
    expect(store.snapshot().videoFullscreen).toBe(false);
    expect(store.runtime.pauseMusic).not.toHaveBeenCalled();
  });

  it.each(["public", "internal"])("an external Steam menu opening exits fullscreen with the %s tree shape", (shape) => {
    const menu = document.implementation.createHTMLDocument("Steam menu");
    let visibility: DocumentVisibilityState = "hidden";
    Object.defineProperty(menu, "visibilityState", { configurable: true, get: () => visibility });
    Object.defineProperty(menu, "hidden", { configurable: true, get: () => visibility === "hidden" });
    platform.trees = [shape === "public"
      ? { id: "MainNavMenuContainer", Root: { Element: menu.body } }
      : { m_ID: "MainNavMenuContainer", m_Root: { m_element: menu.body } }];
    const store = runtimeStore();
    render(<FloatingPlayer />);
    fireEvent.click(fullscreenButton());
    expect(store.snapshot().videoFullscreen).toBe(true);
    act(() => {
      menu.dispatchEvent(new Event("visibilitychange"));
    });
    expect(store.runtime.stopOverlayControl).not.toHaveBeenCalled();
    act(() => {
      visibility = "visible";
      menu.dispatchEvent(new Event("visibilitychange"));
    });
    expect(store.snapshot().videoFullscreen).toBe(false);
    expect(store.snapshot().overlayControl).toBe(false);
    expect(platform.composition).toBe(1);
    expect(store.runtime.pauseMusic).not.toHaveBeenCalled();
  });

  it("unsubscribes from the Steam menu document when the floating player unmounts", () => {
    const menu = document.implementation.createHTMLDocument("Steam menu");
    let visibility: DocumentVisibilityState = "hidden";
    Object.defineProperty(menu, "visibilityState", { configurable: true, get: () => visibility });
    Object.defineProperty(menu, "hidden", { configurable: true, get: () => visibility === "hidden" });
    platform.trees = [{ m_ID: "MainNavMenuContainer", m_Root: { m_element: menu.body } }];
    const store = runtimeStore();
    const mounted = render(<FloatingPlayer />);
    fireEvent.click(fullscreenButton());
    mounted.unmount();
    act(() => {
      visibility = "visible";
      menu.dispatchEvent(new Event("visibilitychange"));
    });
    expect(store.runtime.stopOverlayControl).not.toHaveBeenCalled();
    expect(platform.composition).toBeNull();
  });
});
