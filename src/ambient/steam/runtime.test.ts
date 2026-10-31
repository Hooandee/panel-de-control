// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import defaults from "../../../shared/contracts/ambient/fixtures/defaults.json";
import type { AmbientSettings } from "../core/types";
import type { GameMedia } from "./gameMedia";

const rpcMock = vi.hoisted(() => ({
  getAmbientState: vi.fn(),
  scanAmbientSources: vi.fn(),
  saveAmbientSettings: vi.fn(async (s: unknown) => s),
  getAmbientMediaUrl: vi.fn(async (id: string) => `http://127.0.0.1:1/m/t/${id}`),
  cacheAmbientRemote: vi.fn(),
  reconcileAmbientCache: vi.fn(async () => false),
  getAmbientRemoteFeed: vi.fn(async () => []),
  recordAmbientEvent: vi.fn(async () => true),
  cancelAmbientJobs: vi.fn(async () => true),
  resolveAmbientRadio: vi.fn(async () => null),
  getAmbientSuggestedStations: vi.fn(async () => []),
  searchAmbientRadio: vi.fn(async () => []),
  getAmbientRadioCatalog: vi.fn(),
  discoverAmbientRadio: vi.fn(),
  optimizeAmbientMedia: vi.fn(),
  addAmbientFolder: vi.fn(),
  addAmbientFavorite: vi.fn(),
  removeAmbientItem: vi.fn(),
  restoreAmbientSuggested: vi.fn(),
  setAmbientGameVolume: vi.fn(async () => ({ supported: true, streams: 1 })),
  getAmbientGameMedia: vi.fn(async (): Promise<GameMedia> => ({ trailer: null, theme: null })),
  getAmbientVideoPage: vi.fn(async () => "http://127.0.0.1:9/v/t/player.html"),
}));

vi.mock("./rpc", () => rpcMock);
vi.mock("../../platform/preferences", () => {
  const flags = new Map<string, boolean>();
  return { readFlag: (key: string, fallback: boolean) => flags.get(key) ?? fallback, writeFlag: (key: string, value: boolean) => void flags.set(key, value) };
});
const navigationMock = vi.hoisted(() => ({ CloseSideMenus: vi.fn() }));
vi.mock("@decky/ui", () => ({ findSP: () => ({ document }), Router: {}, Navigation: navigationMock }));
vi.mock("./route", () => ({ currentSurface: () => "home", subscribeSurface: () => () => undefined }));
vi.mock("./steamClasses", () => ({ steamClass: (key: string) => `h-${key}` }));

import { AmbientRuntime, type AmbientPorts } from "./runtime";
import { AmbientThemeChannel } from "./themeChannel";

function settings(patch: Partial<AmbientSettings> = {}): AmbientSettings {
  const base = structuredClone(defaults) as AmbientSettings;
  base.background.enabled = true;
  base.background.collections = ["known.images"];
  return { ...base, ...patch };
}

function ports(inGame = false) {
  const gameListeners: ((g: unknown) => void)[] = [];
  return {
    notify: vi.fn(),
    translate: (key: string, vars?: Record<string, string>) => `${key}${vars?.name ? `:${vars.name}` : ""}`,
    gameSessions: { current: () => (inGame ? { appid: "1", liveAppid: 1, name: "g" } : null), subscribe: (cb: (g: unknown) => void) => { gameListeners.push(cb); return () => undefined; } },
    power: { subscribe: (cb: (s: unknown) => void) => { cb({ battery: null }); return () => undefined; } },
    fireGame: (game: unknown) => gameListeners.forEach((cb) => cb(game)),
  };
}

describe("AmbientRuntime", () => {
  it("retries a failed radio catalog instead of remembering an empty catalog", async () => {
    const runtime = new AmbientRuntime(ports() as unknown as AmbientPorts);
    const catalog = { countries: [{ code: "JP", name: "Japan", count: 3 }], tags: [] };
    rpcMock.getAmbientRadioCatalog.mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce(catalog);
    await expect(runtime.radioCatalog()).rejects.toThrow("offline");
    await expect(runtime.radioCatalog(true)).resolves.toEqual(catalog);
    expect(rpcMock.getAmbientRadioCatalog).toHaveBeenLastCalledWith(true);
  });

  it("keeps a successful empty radio search distinct from a failed request", async () => {
    const runtime = new AmbientRuntime(ports() as unknown as AmbientPorts);
    rpcMock.discoverAmbientRadio.mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce([]);
    await expect(runtime.discoverRadio({ country: "JP" })).rejects.toThrow("offline");
    await expect(runtime.discoverRadio({ country: "JP" })).resolves.toEqual([]);
  });

  it("does not retain a degraded catalog after the network recovers", async () => {
    const runtime = new AmbientRuntime(ports() as unknown as AmbientPorts);
    const degraded = { countries: [], tags: [], error: "catalog_unreachable" };
    const recovered = { countries: [{ code: "JP", name: "Japan", count: 3 }], tags: [] };
    rpcMock.getAmbientRadioCatalog.mockResolvedValueOnce(degraded).mockResolvedValueOnce(recovered);
    await expect(runtime.radioCatalog()).resolves.toEqual(degraded);
    await expect(runtime.radioCatalog()).resolves.toEqual(recovered);
    expect(rpcMock.getAmbientRadioCatalog).toHaveBeenCalledTimes(2);
  });

  it("does not let an older catalog failure evict the successful retry", async () => {
    const runtime = new AmbientRuntime(ports() as unknown as AmbientPorts);
    let rejectOld!: (error: Error) => void;
    const catalog = { countries: [], tags: [] };
    rpcMock.getAmbientRadioCatalog.mockImplementationOnce(() => new Promise((_, reject) => { rejectOld = reject; })).mockResolvedValueOnce(catalog);
    const old = runtime.radioCatalog();
    const rejected = expect(old).rejects.toThrow("old failure");
    await expect(runtime.radioCatalog(true)).resolves.toEqual(catalog);
    rejectOld(new Error("old failure"));
    await rejected;
    await expect(runtime.radioCatalog()).resolves.toEqual(catalog);
    expect(rpcMock.getAmbientRadioCatalog).toHaveBeenCalledTimes(2);
  });

  beforeEach(() => {
    rpcMock.getAmbientRadioCatalog.mockReset();
    rpcMock.discoverAmbientRadio.mockReset();
    rpcMock.saveAmbientSettings.mockImplementation(async (s) => s);
    rpcMock.reconcileAmbientCache.mockResolvedValue(false);
    document.body.innerHTML = '<div class="h-BasicHome"><section></section></div>';
    document.documentElement.removeAttribute("style");
    document.documentElement.removeAttribute("data-pdc-ambient-background");
    rpcMock.scanAmbientSources.mockResolvedValue({ collections: { "known.images": [{ id: "local:a", name: "a.jpg", kind: "image", size: 1, mtime: 1 }] }, music: [], truncated: false });
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    vi.spyOn(HTMLImageElement.prototype, "decode").mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  async function libraryFixture() {
    const configured = settings();
    configured.background.enabled = false;
    configured.music.enabled = false;
    rpcMock.getAmbientState.mockResolvedValue({ settings: configured, knownFolders: {}, collections: [], mediaServer: "stopped" });
    rpcMock.scanAmbientSources.mockResolvedValue({ collections: {}, music: [
      { id: "local:song", name: "Song.mp3", kind: "audio" },
      { id: "local:other", name: "Other.mp3", kind: "audio" },
    ], truncated: false });
    const audio = document.createElement("audio");
    vi.spyOn(audio, "play").mockImplementation(async () => { audio.dispatchEvent(new Event("playing")); });
    vi.spyOn(audio, "pause").mockImplementation(() => { audio.dispatchEvent(new Event("pause")); });
    vi.spyOn(audio, "load").mockImplementation(() => undefined);
    vi.stubGlobal("Audio", function () { return audio; });
    const runtime = new AmbientRuntime(ports() as unknown as AmbientPorts);
    await runtime.start();
    return { runtime, audio };
  }

  function audioStub() {
    const audio = document.createElement("audio");
    vi.spyOn(audio, "play").mockImplementation(async () => { audio.dispatchEvent(new Event("playing")); });
    vi.spyOn(audio, "pause").mockImplementation(() => { audio.dispatchEvent(new Event("pause")); });
    vi.spyOn(audio, "load").mockImplementation(() => undefined);
    vi.stubGlobal("Audio", function () { return audio; });
    return audio;
  }

  it("puts the saved queue back as it was, resolving local songs again", async () => {
    const configured = settings();
    configured.music.enabled = true;
    configured.music.source = "music";
    configured.music.repeat = "one";
    configured.music.queue = [
      { id: "local:song", url: "http://127.0.0.1:1/m/old/local%3Asong", title: "Song", subtitle: "", art: "", kind: "audio", live: false },
      { id: "remote:https://s.test/live", url: "https://s.test/live", title: "Live", subtitle: "", art: "", kind: "audio", live: true },
    ];
    configured.music.lastTrack = { id: "remote:https://s.test/live", position: 0 };
    rpcMock.getAmbientState.mockResolvedValue({ settings: configured, knownFolders: {}, collections: [], mediaServer: "stopped" });
    audioStub();
    const runtime = new AmbientRuntime(ports() as unknown as AmbientPorts);
    try {
      await runtime.start();
      await vi.waitFor(() => expect(runtime.getSnapshot().player.track?.id).toBe("remote:https://s.test/live"));
      const player = runtime.getSnapshot().player;
      expect(player.queue.map((q) => q.track.url)).toEqual(["http://127.0.0.1:1/m/t/local:song", "https://s.test/live"]);
      expect(player.repeat).toBe("one");
    } finally { runtime.stop(); }
  });

  it("a paused queue comes back paused, ready to resume, after a restart", async () => {
    const configured = settings();
    configured.music.enabled = false;
    configured.music.queue = [
      { id: "remote:https://s.test/a", url: "https://s.test/a", title: "A", subtitle: "", art: "", kind: "audio", live: false },
      { id: "remote:https://s.test/b", url: "https://s.test/b", title: "B", subtitle: "", art: "", kind: "audio", live: false },
    ];
    configured.music.lastTrack = { id: "remote:https://s.test/b", position: 12 };
    rpcMock.getAmbientState.mockResolvedValue({ settings: configured, knownFolders: {}, collections: [], mediaServer: "stopped" });
    const audio = audioStub();
    const runtime = new AmbientRuntime(ports() as unknown as AmbientPorts);
    try {
      await runtime.start();
      await vi.waitFor(() => expect(runtime.getSnapshot().player.queue).toHaveLength(2));
      expect(runtime.getSnapshot().player).toMatchObject({ status: "paused", track: { id: "remote:https://s.test/b" } });
      expect(audio.play).not.toHaveBeenCalled();
      runtime.resumeMusic();
      expect(audio.getAttribute("src")).toBe("https://s.test/b");
    } finally { runtime.stop(); }
  });

  it("saves queue changes on top of the saved queue, never an empty one", async () => {
    vi.useFakeTimers();
    const configured = settings();
    configured.music.enabled = false;
    configured.music.queue = [{ id: "remote:https://s.test/a", url: "https://s.test/a", title: "A", subtitle: "", art: "", kind: "audio", live: false }];
    rpcMock.getAmbientState.mockResolvedValue({ settings: configured, knownFolders: {}, collections: [], mediaServer: "stopped" });
    audioStub();
    const runtime = new AmbientRuntime(ports() as unknown as AmbientPorts);
    try {
      await runtime.start();
      await vi.advanceTimersByTimeAsync(3000);
      expect(rpcMock.saveAmbientSettings).not.toHaveBeenCalledWith(expect.objectContaining({ music: expect.objectContaining({ queue: [] }) }));
      runtime.enqueue([
        { id: "remote:https://s.test/b", title: "B", subtitle: "", art: "", url: "https://s.test/b", live: false },
        { id: "remote:https://s.test/c", title: "C", subtitle: "", art: "", url: "https://s.test/c", live: false },
      ]);
      runtime.setShuffle(true);
      await vi.advanceTimersByTimeAsync(2000);
      const calls = rpcMock.saveAmbientSettings.mock.calls;
      const saved = calls[calls.length - 1]?.[0] as AmbientSettings;
      expect(saved.music.queue.map((q) => q.id).sort()).toEqual(["remote:https://s.test/a", "remote:https://s.test/b", "remote:https://s.test/c"]);
      expect(saved.music.shuffle).toBe(true);
    } finally { runtime.stop(); }
  });

  it("a choice made after a library preview survives closing the library", async () => {
    const { runtime } = await libraryFixture();
    try {
      runtime.enqueue([{ id: "remote:https://s.test/mine", title: "Mine", subtitle: "", art: "", url: "https://s.test/mine", live: false }]);
      let end = runtime.beginLibrarySession();
      await runtime.previewLibraryMedia({ ref: "local:song", name: "Song", kind: "audio", collection: "known.music" });
      await runtime.enqueueItems([{ ref: "local:other", name: "Other", kind: "audio", collection: "known.music" }]);
      end();
      expect(runtime.getSnapshot().player.queue.map((q) => q.track.id)).toEqual(["remote:https://s.test/mine", "local:other"]);
      end = runtime.beginLibrarySession();
      await runtime.previewLibraryMedia({ ref: "local:song", name: "Song", kind: "audio", collection: "known.music" });
      runtime.playTracks(await runtime.tracksFor([{ ref: "local:other", name: "Other", kind: "audio", collection: "known.music" }]));
      end();
      expect(runtime.getSnapshot().player.queue.map((q) => q.track.id)).toEqual(["local:other"]);
    } finally { runtime.stop(); }
  });

  it("saves what changed in the library once it closes, even while paused", async () => {
    vi.useFakeTimers();
    const { runtime } = await libraryFixture();
    try {
      runtime.enqueue([{ id: "remote:https://s.test/a", title: "A", subtitle: "", art: "", url: "https://s.test/a", live: false }]);
      runtime.pauseMusic();
      await vi.advanceTimersByTimeAsync(2000);
      const end = runtime.beginLibrarySession();
      await runtime.enqueueItems([{ ref: "local:other", name: "Other", kind: "audio", collection: "known.music" }]);
      end();
      await vi.advanceTimersByTimeAsync(2000);
      const calls = rpcMock.saveAmbientSettings.mock.calls;
      const saved = calls[calls.length - 1]?.[0] as AmbientSettings;
      expect(saved.music.queue.map((q) => q.id)).toEqual(["remote:https://s.test/a", "local:other"]);
    } finally { runtime.stop(); }
  });

  it("does not cache a NASA failure and preserves credits when the feed recovers", async () => {
    const { runtime } = await libraryFixture();
    try {
      rpcMock.getAmbientRemoteFeed.mockRejectedValueOnce(new Error("nasa_unavailable"));
      await expect(runtime.libraryItems("suggested.nasa")).rejects.toThrow("nasa_unavailable");
      rpcMock.getAmbientRemoteFeed.mockResolvedValueOnce([{ url: "https://images-assets.nasa.gov/a.jpg", title: "Nebula", credit: "NASA/ESA" }] as never);
      await expect(runtime.libraryItems("suggested.nasa")).resolves.toEqual([{ ref: "remote:https://images-assets.nasa.gov/a.jpg", kind: "image", name: "Nebula", collection: "suggested.nasa", credit: "NASA/ESA" }]);
    } finally { runtime.stop(); }
  });

  it("keeps local backgrounds available when NASA fails during rebuild", async () => {
    const configured = settings();
    configured.music.enabled = false;
    configured.background.collections = ["suggested.nasa", "known.images"];
    rpcMock.getAmbientState.mockResolvedValue({ settings: configured, knownFolders: {}, collections: [], mediaServer: "stopped" });
    rpcMock.getAmbientRemoteFeed.mockRejectedValueOnce(new Error("nasa_unavailable"));
    const runtime = new AmbientRuntime(ports() as unknown as AmbientPorts);
    try {
      await runtime.start();
      expect(runtime.getSnapshot().error).toBeNull();
      expect(runtime.getSnapshot().items.map(i => i.ref)).toContain("local:a");
    } finally { runtime.stop(); }
  });

  it("releases a failed NASA thumbnail request so a later attempt can recover", async () => {
    const { runtime } = await libraryFixture();
    try {
      runtime.getSnapshot().state!.collections.push({ id: "suggested.nasa", kind: "suggested", source: "nasa-apod" });
      rpcMock.getAmbientRemoteFeed.mockRejectedValueOnce(new Error("nasa_unavailable"));
      runtime.loadPreviews();
      await new Promise(r => setTimeout(r, 10));
      rpcMock.getAmbientRemoteFeed.mockResolvedValueOnce([{ url: "https://images-assets.nasa.gov/a.jpg", title: "Nebula", credit: "NASA" }] as never);
      runtime.loadPreviews();
      await new Promise(r => setTimeout(r, 10));
      expect(runtime.getSnapshot().previews["suggested.nasa"]).toBe("https://images-assets.nasa.gov/a.jpg");
    } finally { runtime.stop(); }
  });

  const librarySong = { ref: "local:preview", name: "Preview.mp3", kind: "audio" as const, collection: "folder.shared" };

  it("rescans folders when the library opens so newly copied files appear", async () => {
    const { runtime } = await libraryFixture();
    try {
      rpcMock.scanAmbientSources.mockResolvedValue({ collections: { "known.images": [{ id: "local:new", name: "auroras.mp4", kind: "video", size: 1, mtime: 2 }] }, music: [], truncated: false });
      const cancel = runtime.beginLibrarySession();
      await vi.waitFor(() => expect(runtime.getSnapshot().scan?.collections["known.images"]?.map((item) => item.id)).toEqual(["local:new"]));
      cancel();
    } finally { runtime.stop(); }
  });

  it.each(["preview", "volume"])("captures playback just before the first %s, preserving progress while browsing", async (firstChange) => {
    const { runtime, audio } = await libraryFixture();
    try {
      await runtime.playSong("local:song");
      const volume = runtime.getSnapshot().player.volume;
      audio.currentTime = 10;
      const cancel = runtime.beginLibrarySession();
      audio.currentTime = 42;
      if (firstChange === "volume") runtime.setVolume(0.2);
      await runtime.previewLibraryMedia(librarySong);
      audio.currentTime = 77;
      await runtime.previewLibraryMedia({ ...librarySong, ref: "local:second" });
      cancel();
      audio.dispatchEvent(new Event("loadedmetadata"));
      expect(audio.currentTime).toBe(42);
      expect(runtime.getSnapshot().player).toMatchObject({ track: { id: "local:song" }, volume, status: "playing" });
    } finally { runtime.stop(); }
  });

  it("previews through the player without persisting controls or timer position, then restores paused playback", async () => {
    vi.useFakeTimers();
    const { runtime, audio } = await libraryFixture();
    try {
      await runtime.playSong("local:song");
      audio.currentTime = 42;
      runtime.pauseMusic();
      await vi.advanceTimersByTimeAsync(0);
      const previous = structuredClone(runtime.getSnapshot().state!.settings);
      rpcMock.saveAmbientSettings.mockClear();
      const cancel = runtime.beginLibrarySession();
      expect(runtime.getSnapshot().libraryOpen).toBe(true);
      await runtime.previewLibraryMedia(librarySong);
      runtime.setVolume(0.2);
      runtime.pauseMusic();
      runtime.resumeMusic();
      runtime.setVideo(false);
      await vi.advanceTimersByTimeAsync(16000);
      expect(rpcMock.saveAmbientSettings).not.toHaveBeenCalled();
      vi.mocked(audio.play).mockClear();
      cancel();
      expect(audio.play).not.toHaveBeenCalled();
      expect(runtime.getSnapshot()).toMatchObject({ libraryOpen: false, player: { status: "paused", track: { id: "local:song" }, position: 42, volume: previous.music.volume } });
      expect(runtime.getSnapshot().state!.settings).toEqual(previous);
      cancel();
      expect(audio.play).not.toHaveBeenCalled();
    } finally { runtime.stop(); }
  });

  it("ignores late URL resolutions after another preview and after cancellation", async () => {
    const { runtime } = await libraryFixture();
    const waiting = new Map<string, (url: string) => void>();
    rpcMock.getAmbientMediaUrl.mockImplementationOnce((id) => new Promise((resolve) => waiting.set(id, resolve)));
    try {
      const cancel = runtime.beginLibrarySession();
      const first = runtime.previewLibraryMedia(librarySong);
      await runtime.previewLibraryMedia({ ...librarySong, ref: "local:second" });
      waiting.get("local:preview")!("http://localhost/old.mp3");
      await first;
      expect(runtime.getSnapshot().player.track?.id).toBe("local:second");
      rpcMock.getAmbientMediaUrl.mockImplementationOnce((id) => new Promise((resolve) => waiting.set(id, resolve)));
      const last = runtime.previewLibraryMedia({ ...librarySong, ref: "local:late" });
      cancel();
      waiting.get("local:late")!("http://localhost/late.mp3");
      await last;
      expect(runtime.getSnapshot()).toMatchObject({ libraryOpen: false, player: { status: "idle", track: null } });
    } finally { runtime.stop(); }
  });

  it("saves the current preview without restarting it and keeps failed saves open", async () => {
    const { runtime, audio } = await libraryFixture();
    try {
      const cancel = runtime.beginLibrarySession();
      await runtime.previewLibraryMedia(librarySong);
      audio.currentTime = 25;
      rpcMock.saveAmbientSettings.mockRejectedValueOnce(new Error("offline"));
      await expect(runtime.saveLibrarySelection([librarySong], "playback")).rejects.toThrow("offline");
      expect(runtime.getSnapshot().libraryOpen).toBe(true);
      const plays = vi.mocked(audio.play).mock.calls.length;
      await runtime.saveLibrarySelection([librarySong], "playback");
      expect(runtime.getSnapshot().libraryOpen).toBe(false);
      expect(runtime.getSnapshot().state!.settings.music.lastTrack).toEqual({ id: librarySong.ref, position: 25 });
      expect(audio.play).toHaveBeenCalledTimes(plays);
      cancel();
      expect(runtime.getSnapshot().player.track?.id).toBe(librarySong.ref);
    } finally { runtime.stop(); }
  });

  it("restores the earlier player after saving a background and preserves the new background", async () => {
    const { runtime } = await libraryFixture();
    try {
      runtime.beginLibrarySession();
      await runtime.previewLibraryMedia(librarySong);
      await runtime.saveLibrarySelection([{ ref: "local:photo", name: "Photo", kind: "image", collection: "folder.shared" }], "background");
      expect(runtime.getSnapshot()).toMatchObject({ libraryOpen: false, player: { status: "idle", track: null } });
      expect(runtime.getSnapshot().state!.settings.background.pinned).toBe("local:photo");
    } finally { runtime.stop(); }
  });

  it("rolls back a save completed after the library was closed without committing player state", async () => {
    const { runtime } = await libraryFixture();
    try {
      const previous = structuredClone(runtime.getSnapshot().state!.settings);
      let finish!: (value: unknown) => void;
      rpcMock.saveAmbientSettings.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
      const cancel = runtime.beginLibrarySession();
      await runtime.previewLibraryMedia(librarySong);
      const saving = runtime.saveLibrarySelection([librarySong], "playback");
      const rejected = expect(saving).rejects.toThrow("library_closed");
      await vi.waitFor(() => expect(finish).toBeTypeOf("function"));
      cancel();
      finish(rpcMock.saveAmbientSettings.mock.calls[rpcMock.saveAmbientSettings.mock.calls.length - 1][0]);
      await rejected;
      expect(rpcMock.saveAmbientSettings).toHaveBeenLastCalledWith(previous);
      expect(runtime.getSnapshot()).toMatchObject({ libraryOpen: false, player: { status: "idle", track: null } });
      expect(runtime.getSnapshot().state!.settings).toEqual(previous);
    } finally { runtime.stop(); }
  });

  it("reports no space once for a remote background and retries only after reload", async () => {
    const configured = settings();
    configured.background.collections = ["favorite.remote"];
    configured.collections.favorites = [{ id: "favorite.remote", name: "Remote", url: "https://example.test/a.jpg" }];
    rpcMock.getAmbientState.mockResolvedValue({ settings: configured, knownFolders: {}, collections: [], mediaServer: "stopped" });
    rpcMock.cacheAmbientRemote.mockResolvedValue({ error: "no_space" });
    const p = ports();
    const runtime = new AmbientRuntime(p as unknown as AmbientPorts);
    try {
      await runtime.start();
      await vi.waitFor(() => expect(runtime.getSnapshot().error).toBe("no_space"));
      runtime.advanceRotation();
      runtime.advanceRotation();
      await Promise.resolve();
      expect(rpcMock.cacheAmbientRemote).toHaveBeenCalledTimes(1);
      expect(rpcMock.cacheAmbientRemote).toHaveBeenCalledWith("https://example.test/a.jpg", "favorite.remote");
      expect(p.notify).toHaveBeenCalledWith("ambient.bg.title", "ambient.error.noSpace");
      rpcMock.cacheAmbientRemote.mockResolvedValue({ id: "cached:a", url: "http://127.0.0.1:1/a.jpg" });
      await runtime.reload();
      await vi.waitFor(() => expect(runtime.getSnapshot().currentUrl).toBe("http://127.0.0.1:1/a.jpg"));
      expect(rpcMock.cacheAmbientRemote).toHaveBeenCalledTimes(2);
      expect(runtime.getSnapshot().error).toBeNull();
    } finally { runtime.stop(); }
  });

  it("reconciles outside games every minute and refreshes served media after cleanup", async () => {
    vi.useFakeTimers();
    rpcMock.getAmbientState.mockResolvedValue({ settings: settings(), knownFolders: {}, collections: [], mediaServer: "stopped" });
    const p = ports();
    const runtime = new AmbientRuntime(p as unknown as AmbientPorts);
    try {
      await runtime.start();
      await vi.advanceTimersByTimeAsync(0);
      expect(rpcMock.reconcileAmbientCache).toHaveBeenCalledTimes(1);
      rpcMock.getAmbientMediaUrl.mockClear();
      rpcMock.reconcileAmbientCache.mockResolvedValue(true);
      await vi.advanceTimersByTimeAsync(60000);
      expect(rpcMock.reconcileAmbientCache).toHaveBeenCalledTimes(2);
      expect(rpcMock.getAmbientMediaUrl).toHaveBeenCalledWith("local:a");
      p.fireGame({ appid: "10" });
      await vi.advanceTimersByTimeAsync(60000);
      expect(rpcMock.reconcileAmbientCache).toHaveBeenCalledTimes(2);
      runtime.stop();
      await vi.advanceTimersByTimeAsync(60000);
      expect(rpcMock.reconcileAmbientCache).toHaveBeenCalledTimes(2);
    } finally { runtime.stop(); }
  });

  it("recovers on its own when the backend is not answering yet at load", async () => {
    vi.useFakeTimers();
    rpcMock.getAmbientState.mockRejectedValueOnce(new Error("backend starting"));
    rpcMock.getAmbientState.mockResolvedValue({ settings: settings(), knownFolders: {}, collections: [], mediaServer: "stopped" });
    const runtime = new AmbientRuntime(ports() as unknown as AmbientPorts);
    try {
      await runtime.start();
      expect(runtime.getSnapshot().error).toBe("backend_unavailable");
      await vi.advanceTimersByTimeAsync(5000);
      expect(runtime.getSnapshot().error).toBeNull();
      expect(runtime.getSnapshot().items.map((item) => item.ref)).toEqual(["local:a"]);
      rpcMock.getAmbientState.mockRejectedValue(new Error("gone"));
      await runtime.reload();
      runtime.stop();
      const calls = rpcMock.getAmbientState.mock.calls.length;
      await vi.advanceTimersByTimeAsync(120000);
      expect(rpcMock.getAmbientState).toHaveBeenCalledTimes(calls);
    } finally { runtime.stop(); }
  });

  it("reports optimization space failures and permits retry after an explicit reload", async () => {
    const configured = settings();
    configured.background.optimizeVideos = true;
    rpcMock.getAmbientState.mockResolvedValue({ settings: configured, knownFolders: {}, collections: [], mediaServer: "stopped" });
    rpcMock.scanAmbientSources.mockResolvedValue({ collections: { "known.images": [{ id: "local:a", name: "a.mp4", kind: "video", size: 1, mtime: 1 }] }, music: [], truncated: false });
    rpcMock.optimizeAmbientMedia.mockResolvedValue({ error: "no_space" });
    const runtime = new AmbientRuntime(ports() as unknown as AmbientPorts);
    const loadVideo = async () => {
      await vi.waitFor(() => expect(document.querySelector("#pdc-ambient-layer video")).not.toBeNull());
      const video = document.querySelector<HTMLVideoElement>("#pdc-ambient-layer video")!;
      Object.defineProperty(video, "videoHeight", { configurable: true, value: 2160 });
      video.dispatchEvent(new Event("loadeddata"));
    };
    try {
      await runtime.start();
      await loadVideo();
      await vi.waitFor(() => expect(runtime.getSnapshot().error).toBe("no_space"));
      runtime.advanceRotation();
      await Promise.resolve();
      expect(rpcMock.optimizeAmbientMedia).toHaveBeenCalledTimes(1);
      await runtime.reload();
      await loadVideo();
      await vi.waitFor(() => expect(rpcMock.optimizeAmbientMedia).toHaveBeenCalledTimes(2));
    } finally { runtime.stop(); }
  });

  it("does not reconcile on startup during a game", async () => {
    rpcMock.getAmbientState.mockResolvedValue({ settings: settings(), knownFolders: {}, collections: [], mediaServer: "stopped" });
    const runtime = new AmbientRuntime(ports(true) as unknown as AmbientPorts);
    try {
      await runtime.start();
      expect(rpcMock.reconcileAmbientCache).not.toHaveBeenCalled();
    } finally { runtime.stop(); }
  });

  it("releases removed background URLs and selects a surviving item", async () => {
    const configured = settings();
    rpcMock.getAmbientState.mockResolvedValue({ settings: configured, knownFolders: {}, collections: [], mediaServer: "stopped" });
    const runtime = new AmbientRuntime(ports() as unknown as AmbientPorts);
    try {
      await runtime.start();
      await vi.waitFor(() => expect(runtime.getSnapshot().currentUrl).toContain("local:a"));
      rpcMock.removeAmbientItem.mockResolvedValue(configured);
      rpcMock.scanAmbientSources.mockResolvedValue({ collections: { "known.images": [{ id: "local:b", name: "b.jpg", kind: "image", size: 1, mtime: 1 }] }, music: [], truncated: false });
      await runtime.removeItem("background", "favorite.removed");
      await vi.waitFor(() => expect(runtime.getSnapshot().currentUrl).toContain("local:b"));
      expect(runtime.getSnapshot().current?.ref).toBe("local:b");
    } finally { runtime.stop(); }
  });

  it("paints the background and marks the document when Panel owns it", async () => {
    rpcMock.getAmbientState.mockResolvedValue({ settings: settings(), knownFolders: {}, collections: [], mediaServer: "stopped" });
    const runtime = new AmbientRuntime(ports() as unknown as AmbientPorts);
    await runtime.start();
    await vi.waitFor(() => expect(document.getElementById("pdc-ambient-layer")).not.toBeNull());
    expect(document.documentElement.getAttribute("data-pdc-ambient-background")).toBe("panel");
    expect(runtime.getSnapshot().current?.ref).toBe("local:a");
    runtime.stop();
    expect(document.getElementById("pdc-ambient-layer")).toBeNull();
    expect(document.documentElement.hasAttribute("data-pdc-ambient-background")).toBe(false);
  });

  it("a cooperative theme claim without a choice keeps the theme and notifies once", async () => {
    document.documentElement.style.setProperty("--pdc-ambient-claim", "hooandee-gallery");
    document.documentElement.style.setProperty("--pdc-ambient-claim-name", "Gallery");
    rpcMock.getAmbientState.mockResolvedValue({ settings: settings(), knownFolders: {}, collections: [], mediaServer: "stopped" });
    const p = ports();
    const runtime = new AmbientRuntime(p as unknown as AmbientPorts);
    await runtime.start();
    await vi.waitFor(() => expect(runtime.getSnapshot().decision.conflict?.id).toBe("hooandee-gallery"));
    runtime.advanceRotation();
    await new Promise((r) => setTimeout(r, 10));
    expect(p.notify).toHaveBeenCalledTimes(1);
    expect(p.notify).toHaveBeenCalledWith("ambient.toast.theme:Gallery", "ambient.toast.body");
    expect(document.getElementById("pdc-ambient-layer")).toBeNull();
    runtime.stop();
  });

  it("choosing Panel for that theme paints ours and clears the conflict", async () => {
    document.documentElement.style.setProperty("--pdc-ambient-claim", "hooandee-gallery");
    rpcMock.getAmbientState.mockResolvedValue({ settings: settings(), knownFolders: {}, collections: [], mediaServer: "stopped" });
    const runtime = new AmbientRuntime(ports() as unknown as AmbientPorts);
    await runtime.start();
    await runtime.choose("hooandee-gallery", "panel");
    await vi.waitFor(() => expect(runtime.getSnapshot().decision).toMatchObject({ background: "panel", conflict: null }));
    await vi.waitFor(() => expect(document.getElementById("pdc-ambient-layer")).not.toBeNull());
    expect(rpcMock.saveAmbientSettings).toHaveBeenLastCalledWith(expect.objectContaining({ claims: { "hooandee-gallery": "panel" } }));
    runtime.stop();
  });

  it("entering a game pauses the video layer and leaves the game's volume alone", async () => {
    rpcMock.getAmbientState.mockResolvedValue({ settings: settings(), knownFolders: {}, collections: [], mediaServer: "stopped" });
    const p = ports();
    const runtime = new AmbientRuntime(p as unknown as AmbientPorts);
    await runtime.start();
    p.fireGame({ appid: "1" });
    await vi.waitFor(() => expect(runtime.getSnapshot().motion).toBe("pause"));
    expect(rpcMock.setAmbientGameVolume).not.toHaveBeenCalled();
    runtime.stop();
  });

  it("reports a backend failure instead of pretending", async () => {
    rpcMock.getAmbientState.mockRejectedValue(new Error("down"));
    const runtime = new AmbientRuntime(ports() as unknown as AmbientPorts);
    await runtime.start();
    expect(runtime.getSnapshot()).toMatchObject({ ready: true, error: "backend_unavailable" });
    runtime.stop();
  });

  it("a runtime theme in host mode paints Panel's background itself", async () => {
    rpcMock.getAmbientState.mockResolvedValue({ settings: settings({ claims: { "hooandee-gallery": "panel" } }), knownFolders: {}, collections: [], mediaServer: "stopped" });
    const channel = new AmbientThemeChannel();
    channel.claim("hooandee-gallery", { name: "Gallery", surfaces: ["home"], mode: "host" });
    const states: unknown[] = [];
    channel.subscribe((s) => states.push(s));
    const runtime = new AmbientRuntime(ports() as unknown as AmbientPorts, channel);
    await runtime.start();
    await vi.waitFor(() => expect(channel.getState()).toMatchObject({ owner: "panel", media: { url: "http://127.0.0.1:1/m/t/local:a", kind: "image" } }));
    expect(document.getElementById("pdc-ambient-layer")).toBeNull();
    expect(runtime.getSnapshot().decision.conflict).toBeNull();
    runtime.stop();
    expect(channel.getState().owner).toBe("theme");
  });

  it("keeping mine over a third-party painter clears only that painter's background", async () => {
    rpcMock.getAmbientState.mockResolvedValue({ settings: settings({ claims: { "css:ScrollArea::before": "panel" } }), knownFolders: {}, collections: [], mediaServer: "stopped" });
    const runtime = new AmbientRuntime(ports() as unknown as AmbientPorts);
    await runtime.start();
    await vi.waitFor(() => expect(document.getElementById("pdc-ambient-neutralize")?.textContent).toContain(".h-ScrollArea::before{background:none!important"));
    runtime.stop();
    expect(document.getElementById("pdc-ambient-neutralize")).toBeNull();
  });

  it("an older save response never overwrites a newer choice", async () => {
    rpcMock.getAmbientState.mockResolvedValue({ settings: settings(), knownFolders: {}, collections: [], mediaServer: "stopped" });
    const resolvers: ((s: unknown) => void)[] = [];
    rpcMock.saveAmbientSettings.mockImplementation((s: unknown) => new Promise((resolve) => resolvers.push(() => resolve(s))));
    const runtime = new AmbientRuntime(ports() as unknown as AmbientPorts);
    await runtime.start();
    const first = runtime.updateSettings((s) => ({ ...s, music: { ...s.music, volume: 0.2 } }));
    const second = runtime.updateSettings((s) => ({ ...s, music: { ...s.music, volume: 0.9 } }));
    await vi.waitFor(() => expect(resolvers.length).toBe(1));
    resolvers[0](undefined);
    await vi.waitFor(() => expect(resolvers.length).toBe(2));
    resolvers[1](undefined);
    await Promise.all([first, second]);
    expect(runtime.getSnapshot().state?.settings.music.volume).toBe(0.9);
    rpcMock.saveAmbientSettings.mockImplementation(async (s: unknown) => s);
    runtime.stop();
  });

  it("a kept background stays put and browsing makes the reached one the kept one", async () => {
    rpcMock.scanAmbientSources.mockResolvedValue({ collections: { "known.images": ["a", "b", "c"].map((n) => ({ id: `local:${n}`, name: `${n}.jpg`, kind: "image", size: 1, mtime: 1 })) }, music: [], truncated: false });
    const pinned = settings();
    pinned.background.pinned = "local:b";
    rpcMock.getAmbientState.mockResolvedValue({ settings: pinned, knownFolders: {}, collections: [], mediaServer: "stopped" });
    const runtime = new AmbientRuntime(ports() as unknown as AmbientPorts);
    await runtime.start();
    await vi.waitFor(() => expect(runtime.getSnapshot().current?.ref).toBe("local:b"));
    runtime.advanceRotation();
    expect(runtime.getSnapshot().current?.ref).toBe("local:b");
    runtime.stepBackground(1);
    expect(runtime.getSnapshot().current?.ref).toBe("local:c");
    await vi.waitFor(() => expect(runtime.getSnapshot().state?.settings.background.pinned).toBe("local:c"));
    await runtime.setPinned(false);
    expect(runtime.getSnapshot().state?.settings.background.pinned).toBe("");
    runtime.stop();
  });

  it("a game resting selected on Home plays its trailer as the background, capped to a light rendition", async () => {
    document.body.innerHTML = '<div class="h-BasicHome"><section></section><div class="h-RecentGamesContainer"><img src="https://steamloopback.host/assets/1145360/library_hero_blur.jpg?c=0"></div></div>';
    rpcMock.getAmbientGameMedia.mockResolvedValue({ trailer: { url: "https://video.akamai.steamstatic.com/a.m3u8", poster: "", title: "" }, theme: null });
    const trailers = settings();
    trailers.background.gameTrailers = true;
    rpcMock.getAmbientState.mockResolvedValue({ settings: trailers, knownFolders: {}, collections: [], mediaServer: "stopped" });
    const runtime = new AmbientRuntime(ports() as unknown as AmbientPorts);
    await runtime.start();
    const frame = await vi.waitFor(() => {
      const found = document.querySelector<HTMLIFrameElement>("#pdc-ambient-layer iframe");
      if (!found) throw new Error("no trailer yet");
      return found;
    }, { timeout: 4000 });
    const url = new URL(frame.src);
    expect(url.searchParams.get("src")).toBe("https://video.akamai.steamstatic.com/a.m3u8");
    expect(url.searchParams.get("maxh")).toBe("360");
    expect(url.searchParams.get("vol")).toBe("0");
    expect(rpcMock.getAmbientGameMedia).toHaveBeenCalledWith("1145360", expect.any(String), true);
    await runtime.updateSettings((s) => ({ ...s, background: { ...s.background, enabled: false } }));
    await vi.waitFor(() => expect(document.querySelector("#pdc-ambient-layer iframe")).toBeNull());
    expect(runtime.getSnapshot().state?.settings.background.gameTrailers).toBe(true);
    await runtime.updateSettings((s) => ({ ...s, background: { ...s.background, enabled: true } }));
    await vi.waitFor(() => expect(document.querySelector("#pdc-ambient-layer iframe")).not.toBeNull(), { timeout: 3000 });
    runtime.stop();
  });

  it("music the user puts on silences the selected game's soundtrack until another game is selected", async () => {
    const home = (appid: string) => { document.body.innerHTML = `<div class="h-BasicHome"><section></section><div class="h-RecentGamesContainer"><img src="https://steamloopback.host/assets/${appid}/library_hero_blur.jpg"></div></div>`; };
    home("1145360");
    const THEME = "https://audio.test/theme.m4a";
    rpcMock.getAmbientGameMedia.mockResolvedValue({ trailer: null, theme: { url: THEME, title: "Theme", artist: "" } });
    const configured = settings();
    configured.background.gameThemes = true;
    configured.music.enabled = false;
    rpcMock.getAmbientState.mockResolvedValue({ settings: configured, knownFolders: {}, collections: [], mediaServer: "stopped" });
    rpcMock.scanAmbientSources.mockResolvedValue({ collections: {}, music: [{ id: "local:song", name: "Song.mp3", kind: "audio" }], truncated: false });
    const elements: HTMLAudioElement[] = [];
    vi.stubGlobal("Audio", function () {
      const audio = document.createElement("audio");
      vi.spyOn(audio, "play").mockImplementation(async () => { audio.dispatchEvent(new Event("playing")); });
      vi.spyOn(audio, "pause").mockImplementation(() => { audio.dispatchEvent(new Event("pause")); });
      vi.spyOn(audio, "load").mockImplementation(() => undefined);
      elements.push(audio);
      return audio;
    });
    const themePlays = () => elements.flatMap((audio) => vi.mocked(audio.play).mock.instances.length && audio.getAttribute("src") === THEME ? [audio] : []);
    const runtime = new AmbientRuntime(ports() as unknown as AmbientPorts);
    try {
      await runtime.start();
      await vi.waitFor(() => expect(themePlays()).toHaveLength(1), { timeout: 10000 });
      await runtime.playSong("local:song");
      await vi.waitFor(() => expect(themePlays()).toHaveLength(0), { timeout: 10000 });
      await runtime.updateSettings((s) => s);
      await new Promise((done) => setTimeout(done, 1800));
      expect(themePlays()).toHaveLength(0);
      expect(runtime.getSnapshot().player.status).toBe("playing");
      home("413150");
      await runtime.updateSettings((s) => s);
      await vi.waitFor(() => expect(themePlays()).toHaveLength(1), { timeout: 10000 });
    } finally { runtime.stop(); }
  }, 30000);

  it("a theme with its own Home plays no game soundtrack from Steam's hidden carousel", async () => {
    const home = (style: string) => { document.body.innerHTML = `<div class="h-BasicHome"><section></section><div style="${style}"><div class="h-RecentGamesContainer"><img src="https://steamloopback.host/assets/413150/library_hero_blur.jpg"></div></div></div>`; };
    rpcMock.getAmbientGameMedia.mockResolvedValue({ trailer: { url: "https://video.akamai.steamstatic.com/a.m3u8", poster: "", title: "" }, theme: { url: "https://audio.test/theme.m4a", title: "Theme", artist: "" } });
    const configured = settings();
    configured.background.gameThemes = true;
    configured.background.gameTrailers = true;
    rpcMock.getAmbientState.mockResolvedValue({ settings: configured, knownFolders: {}, collections: [], mediaServer: "stopped" });
    const quiet = async (channel?: AmbientThemeChannel) => {
      const runtime = new AmbientRuntime(ports() as unknown as AmbientPorts, channel);
      try {
        await runtime.start();
        await runtime.updateSettings((s) => s);
        await new Promise((done) => setTimeout(done, 300));
        expect(runtime.getSnapshot().selectedGame).toBeNull();
        expect(rpcMock.getAmbientGameMedia).not.toHaveBeenCalled();
        expect(document.querySelector("#pdc-ambient-layer iframe")).toBeNull();
      } finally { runtime.stop(); }
    };
    home("opacity: 0");
    await quiet();
    home("");
    const channel = new AmbientThemeChannel();
    channel.claim("hooandee-bubble", { name: "Bubble", surfaces: ["home"], mode: "yield" });
    await quiet(channel);
  });

  it("says when Decky never draws the floating player, and not when it does", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    rpcMock.getAmbientState.mockResolvedValue({ settings: settings(), knownFolders: {}, collections: [], mediaServer: "stopped" });
    const missing = new AmbientRuntime(ports() as unknown as AmbientPorts);
    const drawn = new AmbientRuntime(ports() as unknown as AmbientPorts);
    try {
      await missing.start();
      await drawn.start();
      const release = drawn.markFloatingMounted();
      await vi.advanceTimersByTimeAsync(6500);
      expect(missing.getSnapshot().floatingMissing).toBe(true);
      expect(rpcMock.recordAmbientEvent).toHaveBeenCalledWith("floating_missing", expect.any(String));
      expect(drawn.getSnapshot().floatingMissing).toBe(false);
      missing.markFloatingMounted();
      expect(missing.getSnapshot().floatingMissing).toBe(false);
      release();
    } finally { missing.stop(); drawn.stop(); }
  });

  it("does not restore a pending trailer after the background is switched off", async () => {
    document.body.innerHTML = '<div class="h-BasicHome"><section></section><div class="h-RecentGamesContainer"><img src="https://steamloopback.host/assets/1145360/library_hero_blur.jpg"></div></div>';
    let resolve!: (media: GameMedia) => void;
    rpcMock.getAmbientGameMedia.mockImplementationOnce(() => new Promise<GameMedia>((done) => { resolve = done; }));
    const configured = settings();
    configured.background.gameTrailers = true;
    rpcMock.getAmbientState.mockResolvedValue({ settings: configured, knownFolders: {}, collections: [], mediaServer: "stopped" });
    const runtime = new AmbientRuntime(ports() as unknown as AmbientPorts);
    try {
      await runtime.start();
      await vi.waitFor(() => expect(resolve).toBeDefined(), { timeout: 3000 });
      await runtime.updateSettings((s) => ({ ...s, background: { ...s.background, enabled: false } }));
      resolve({ trailer: { url: "https://example.test/late.m3u8", poster: "", title: "" }, theme: null });
      await new Promise((done) => setTimeout(done, 50));
      expect(document.querySelector("#pdc-ambient-layer iframe")).toBeNull();
    } finally { runtime.stop(); }
  });

  it("rotates only chosen photos across reload and returns to a single photo or whole collection", async () => {
    const configured = settings();
    const media = ["a", "b", "c"].map((id) => ({ id: `local:${id}`, name: `${id}.jpg`, kind: "image", size: 1, mtime: 1 }));
    const state = { settings: configured, knownFolders: {}, collections: [], mediaServer: "stopped" };
    rpcMock.getAmbientState.mockImplementation(async () => structuredClone(state));
    rpcMock.saveAmbientSettings.mockImplementation(async (s) => { state.settings = s as AmbientSettings; return s; });
    rpcMock.scanAmbientSources.mockResolvedValue({ collections: { "known.images": media }, music: [], truncated: false });
    const runtime = new AmbientRuntime(ports() as unknown as AmbientPorts);
    try {
      await runtime.start();
      const available = await runtime.libraryItems("known.images");
      await runtime.useBackgroundSelection([available[0], available[2]]);
      expect(runtime.getSnapshot().items.map((i) => i.ref)).toEqual(["local:a", "local:c"]);
      expect(state.settings.background.pinned).toBe("");
      await runtime.reload();
      for (let i = 0; i < 5; i++) {
        runtime.advanceRotation();
        expect(["local:a", "local:c"]).toContain(runtime.getSnapshot().current?.ref);
      }
      await runtime.useBackground(available[1]);
      expect(runtime.getSnapshot().current?.ref).toBe("local:b");
      expect(state.settings.background.selectedRefs).toEqual([]);
      await runtime.useBackgroundSelection([available[0], available[2]]);
      await runtime.toggleCollection("known.images", true);
      expect(runtime.getSnapshot().items).toHaveLength(3);
      expect(state.settings.background.selectedRefs).toEqual([]);
    } finally { runtime.stop(); }
  });

  it("no conflict is announced while the background is off", async () => {
    document.documentElement.style.setProperty("--pdc-ambient-claim", "hooandee-gallery");
    const off = settings();
    off.background.enabled = false;
    rpcMock.getAmbientState.mockResolvedValue({ settings: off, knownFolders: {}, collections: [], mediaServer: "stopped" });
    const p = ports();
    const runtime = new AmbientRuntime(p as unknown as AmbientPorts);
    await runtime.start();
    await new Promise((r) => setTimeout(r, 20));
    expect(runtime.getSnapshot().decision.conflict).toBeNull();
    expect(p.notify).not.toHaveBeenCalled();
    runtime.stop();
  });

  it("a painter only raises a conflict after it settles, never during a theme remount", async () => {
    rpcMock.getAmbientState.mockResolvedValue({ settings: settings(), knownFolders: {}, collections: [], mediaServer: "stopped" });
    const style = document.createElement("style");
    style.className = "css-loader-style";
    document.head.appendChild(style);
    const painter = document.createElement("div");
    painter.className = "h-ScrollArea";
    painter.style.backgroundImage = "linear-gradient(red, blue)";
    painter.getBoundingClientRect = () => ({ x: 0, y: 0, width: window.innerWidth, height: window.innerHeight, top: 0, left: 0, right: 0, bottom: 0, toJSON: () => ({}) });
    document.body.appendChild(painter);
    const p = ports();
    const runtime = new AmbientRuntime(p as unknown as AmbientPorts, undefined, 150);
    await runtime.start();
    await new Promise((r) => setTimeout(r, 40));
    expect(runtime.getSnapshot().decision.conflict).toBeNull();
    await vi.waitFor(() => expect(runtime.getSnapshot().decision.conflict?.kind).toBe("other"), { timeout: 2000 });
    expect(p.notify).toHaveBeenCalledTimes(1);
    runtime.stop();
    style.remove();
    painter.remove();
  });

  it("chooses a specific photo from a shared source outside the rotation and keeps it after reload", async () => {
    const configured = settings();
    const folder = "folder.shared";
    const items = [
      { id: "local:first", name: "first.jpg", kind: "image", size: 1, mtime: 1 },
      { id: "local:chosen", name: "chosen.jpg", kind: "image", size: 1, mtime: 1 },
      { id: "local:audio", name: "song.mp3", kind: "audio", size: 1, mtime: 1 },
    ];
    const state = { settings: configured, knownFolders: {}, collections: [{ id: folder, kind: "folder", name: "Shared" }], mediaServer: "stopped" };
    rpcMock.getAmbientState.mockImplementation(async () => structuredClone(state));
    rpcMock.saveAmbientSettings.mockImplementation(async (saved: unknown) => { state.settings = saved as AmbientSettings; return saved; });
    rpcMock.scanAmbientSources.mockResolvedValue({ collections: { [folder]: items.slice(0, 2) }, library: { [folder]: items }, music: [items[2]], truncated: false });
    const runtime = new AmbientRuntime(ports() as unknown as AmbientPorts);
    try {
      await runtime.start();
      const available = await runtime.libraryItems(folder);
      expect(available.map((item) => item.ref)).toEqual(["local:first", "local:chosen"]);
      await runtime.useBackground(available[1]);
      expect(runtime.getSnapshot().current?.ref).toBe("local:chosen");
      expect(state.settings.background.pinned).toBe("local:chosen");
      await runtime.reload();
      expect(runtime.getSnapshot().current?.ref).toBe("local:chosen");
      expect(state.settings.background.collections).toContain(folder);
    } finally { runtime.stop(); }
  });

  it("shares visual links saved from Multimedia without adding a second favorite", async () => {
    const configured = settings();
    configured.radio.favorites = [{ id: "fav.shared", name: "Video", url: "https://example.test/movie.mp4" }];
    rpcMock.getAmbientState.mockResolvedValue({ settings: configured, knownFolders: {}, collections: [], mediaServer: "stopped" });
    const runtime = new AmbientRuntime(ports() as unknown as AmbientPorts);
    try {
      await runtime.start();
      expect(await runtime.libraryItems("fav.shared")).toEqual([{ ref: "remote:https://example.test/movie.mp4", name: "Video", kind: "video", collection: "fav.shared" }]);
      expect(rpcMock.addAmbientFavorite).not.toHaveBeenCalled();
    } finally { runtime.stop(); }
  });

  it.each([false, true])("removes a daily pin before its first successful download; other owner=%s", async (shared) => {
    const configured = settings();
    const url = "https://example.test/daily.jpg";
    const ref = `remote:${url}`;
    configured.background.collections = ["suggested.nasa", ...(shared ? ["fav.same"] : [])];
    configured.background.pinned = ref;
    if (shared) configured.collections.favorites = [{ id: "fav.same", name: "Same", url }];
    const state = { settings: configured, knownFolders: {}, collections: [], mediaServer: "stopped" };
    rpcMock.getAmbientState.mockImplementation(async () => structuredClone(state));
    rpcMock.saveAmbientSettings.mockImplementation(async (saved: unknown) => { state.settings = saved as AmbientSettings; return saved; });
    rpcMock.getAmbientRemoteFeed.mockResolvedValue([{ url, title: "Daily" }] as never);
    rpcMock.cacheAmbientRemote.mockResolvedValue({ error: "no_space" });
    rpcMock.removeAmbientItem.mockImplementation(async () => {
      state.settings = { ...state.settings, background: { ...state.settings.background, collections: state.settings.background.collections.filter((c) => c !== "suggested.nasa") } };
      return structuredClone(state.settings);
    });
    const runtime = new AmbientRuntime(ports() as unknown as AmbientPorts);
    try {
      await runtime.start();
      await vi.waitFor(() => expect(runtime.getSnapshot().error).toBe("no_space"));
      expect(await runtime.removeItem("background", "suggested.nasa")).toBe(true);
      await runtime.reload();
      expect(runtime.getSnapshot().state?.settings.background.pinned).toBe(shared ? ref : "");
    } finally { runtime.stop(); }
  });

  it("keeps the library session open through fullscreen while retaining side-menu dismissal outside it", async () => {
    const { runtime } = await libraryFixture();
    rpcMock.getAmbientVideoPage.mockImplementationOnce(() => new Promise<string>(() => undefined));
    try {
      runtime.setVideo(true);
      runtime.playStation({ id: "tv", name: "TV", url: "https://tv.test/live.m3u8", favicon: "", country: "", countryCode: "", tags: [], codec: "", bitrate: 0 }, false);
      const cancel = runtime.beginLibrarySession();
      runtime.setVideoFullscreen(true);
      expect(runtime.getSnapshot()).toMatchObject({ libraryOpen: true, videoFullscreen: true, overlayControl: true });
      expect(navigationMock.CloseSideMenus).not.toHaveBeenCalled();
      runtime.setVideoFullscreen(false);
      expect(runtime.getSnapshot()).toMatchObject({ libraryOpen: true, videoFullscreen: false, overlayControl: false });
      expect(navigationMock.CloseSideMenus).not.toHaveBeenCalled();
      cancel();
      runtime.setVideoFullscreen(true);
      expect(runtime.getSnapshot()).toMatchObject({ libraryOpen: false, videoFullscreen: true, overlayControl: true });
      expect(navigationMock.CloseSideMenus).toHaveBeenCalledOnce();
    } finally { runtime.stop(); }
  });

  it("fullscreen is temporary and leaving for a Steam menu releases input atomically", async () => {
    const configured = settings();
    rpcMock.getAmbientState.mockResolvedValue({ settings: configured, knownFolders: {}, collections: [], mediaServer: "stopped" });
    const runtime = new AmbientRuntime(ports() as unknown as AmbientPorts);
    try {
      await runtime.start();
      runtime.setVideo(true);
      runtime.playStation({ id: "tv", name: "TV", url: "https://tv.test/live.m3u8", favicon: "", country: "", countryCode: "", tags: [], codec: "", bitrate: 0 }, false);
      const before = structuredClone(runtime.getSnapshot().state?.settings);
      runtime.setVideoFullscreen(true);
      expect(runtime.getSnapshot()).toMatchObject({ videoFullscreen: true, overlayControl: true });
      runtime.setVideoFullscreen(false);
      expect(runtime.getSnapshot()).toMatchObject({ videoFullscreen: false, overlayControl: false });
      runtime.startOverlayControl();
      runtime.setVideoFullscreen(true);
      runtime.setVideoFullscreen(false);
      expect(runtime.getSnapshot().overlayControl).toBe(true);
      runtime.setVideoFullscreen(true);
      runtime.stopOverlayControl("quick-access");
      expect(runtime.getSnapshot()).toMatchObject({ videoFullscreen: false, overlayControl: false });
      expect(runtime.getSnapshot().state?.settings).toEqual(before);
    } finally { runtime.stop(); }
  });

});
