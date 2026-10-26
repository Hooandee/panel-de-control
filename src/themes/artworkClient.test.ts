import { describe, expect, it, vi } from "vitest";
import { DEFAULT_ARTWORK } from "./artwork";
import { artworkAccess, artworkThemeActive, configureArtworkHost, loadArtwork, saveArtwork, startArtworkHydration, getGeneralArtwork, getCustomArtwork, saveGeneralArtwork } from "./artworkClient";

describe("artwork cache", () => {
  it("publishes loaded, saved and reset values, while failed saves keep prior state", async () => {
    const write = vi.fn(async () => ({ ok: true }));
    const release = configureArtworkHost({ read: async () => ({ "1": { ...DEFAULT_ARTWORK, positionX: 25 } }), write });
    const changed = vi.fn();
    const unsubscribe = artworkAccess.subscribe(changed);
    await loadArtwork();
    expect(artworkAccess.get(1)?.positionX).toBe(25);
    await saveArtwork(1, { ...DEFAULT_ARTWORK, positionX: 70 });
    expect(artworkAccess.get(1)?.positionX).toBe(70);
    write.mockResolvedValueOnce({ ok: false });
    await expect(saveArtwork(1, DEFAULT_ARTWORK)).rejects.toThrow();
    expect(artworkAccess.get(1)?.positionX).toBe(70);
    await saveArtwork(1, null);
    expect(artworkAccess.get(1)).toBeNull();
    expect(changed).toHaveBeenCalledTimes(3);
    unsubscribe(); release();
  });
  it("does not publish a load after host disposal", async () => {
    let resolve!: (value: Record<string, typeof DEFAULT_ARTWORK>) => void;
    const release = configureArtworkHost({ read: () => new Promise((done) => { resolve = done; }), write: async () => ({ ok: true }) });
    const loaded = loadArtwork();
    await Promise.resolve();
    release();
    resolve({ "1": DEFAULT_ARTWORK });
    await expect(loaded).rejects.toThrow("artwork_host_replaced");
    expect(artworkAccess.get(1)).toBeNull();
  });
});

describe("startup artwork recovery", () => {
  it("recovers a transient initial RPC failure and publishes saved artwork", async () => {
    vi.useFakeTimers();
    const read = vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValue({ "9": { ...DEFAULT_ARTWORK, positionX: 77 } });
    const release = configureArtworkHost({ read, write: async () => ({ ok: true }) });
    const changed = vi.fn();
    const unsubscribe = artworkAccess.subscribe(changed);
    const stop = startArtworkHydration();
    try {
      await vi.advanceTimersByTimeAsync(1000);
      expect(read).toHaveBeenCalledTimes(2);
      expect(artworkAccess.get(9)?.positionX).toBe(77);
      expect(changed).toHaveBeenCalledOnce();
      await vi.advanceTimersByTimeAsync(30000);
      expect(read).toHaveBeenCalledTimes(2);
    } finally { stop(); unsubscribe(); release(); vi.useRealTimers(); }
  });
  it("bounds retries and cancels the pending timer on unload", async () => {
    vi.useFakeTimers();
    const read = vi.fn().mockRejectedValue(new Error("offline"));
    const release = configureArtworkHost({ read, write: async () => ({ ok: true }) });
    const stop = startArtworkHydration();
    try {
      await vi.advanceTimersByTimeAsync(30000);
      expect(read).toHaveBeenCalledTimes(4);
      stop();
      const stopAgain = startArtworkHydration();
      await vi.advanceTimersByTimeAsync(0);
      expect(read).toHaveBeenCalledTimes(5);
      stopAgain(); release();
      await vi.advanceTimersByTimeAsync(30000);
      expect(read).toHaveBeenCalledTimes(5);
    } finally { stop(); release(); vi.useRealTimers(); }
  });
  it("never notifies subscribers for an in-flight response after unload", async () => {
    vi.useFakeTimers();
    let resolve!: (value: Record<string, typeof DEFAULT_ARTWORK>) => void;
    const read = vi.fn(() => new Promise<Record<string, typeof DEFAULT_ARTWORK>>((done) => { resolve = done; }));
    const release = configureArtworkHost({ read, write: async () => ({ ok: true }) });
    const changed = vi.fn();
    const unsubscribe = artworkAccess.subscribe(changed);
    const stop = startArtworkHydration();
    try {
      await vi.advanceTimersByTimeAsync(0);
      stop(); release();
      resolve({ "9": DEFAULT_ARTWORK });
      await vi.advanceTimersByTimeAsync(30000);
      expect(changed).not.toHaveBeenCalled();
      expect(read).toHaveBeenCalledOnce();
      expect(artworkAccess.get(9)).toBeNull();
    } finally { stop(); unsubscribe(); release(); vi.useRealTimers(); }
  });
});

describe("general artwork inheritance", () => {
  it("inherits defaults, preserves game overrides, and resets back to inheritance", async () => {
    const write = vi.fn(async () => ({ok: true}));
    const release = configureArtworkHost({read: async () => ({"8": {...DEFAULT_ARTWORK, positionX: 15}}), write});
    try {
      await loadArtwork();
      expect(getGeneralArtwork()).toEqual({...DEFAULT_ARTWORK, showTitle: false});
      expect(getCustomArtwork(9)).toBeNull();
      expect(artworkAccess.get(9)).toBeNull();
      await saveGeneralArtwork({...DEFAULT_ARTWORK, positionX: 70});
      expect(write).toHaveBeenLastCalledWith(0, {...DEFAULT_ARTWORK, positionX: 70});
      expect(artworkAccess.get(9)?.positionX).toBe(70);
      expect(artworkAccess.get(8)?.positionX).toBe(15);
      await saveArtwork(8, null);
      expect(getCustomArtwork(8)).toBeNull();
      expect(artworkAccess.get(8)?.positionX).toBe(70);
      await saveGeneralArtwork(null);
      expect(artworkAccess.get(8)).toBeNull();
      expect(getGeneralArtwork()).toEqual({...DEFAULT_ARTWORK, showTitle: false});
    } finally {release();}
  });
  it("loads existing game records alongside general settings and rejects a general image", async () => {
    const write = vi.fn(async () => ({ok: true}));
    const release = configureArtworkHost({read: async () => ({"0": {...DEFAULT_ARTWORK, showLogo: false}, "7": {...DEFAULT_ARTWORK, image: 'https://steamloopback.host/assets/7.jpg'}}), write});
    try {
      await loadArtwork();
      expect(artworkAccess.get(8)?.showLogo).toBe(false);
      expect(getCustomArtwork(7)?.image).toContain('/7.jpg');
      await expect(saveGeneralArtwork({...DEFAULT_ARTWORK, image: 'https://steamloopback.host/assets/7.jpg'})).rejects.toThrow('invalid_general_image');
      expect(write).not.toHaveBeenCalled();
    } finally {release();}
  });
});

it("serializes concurrent saves and allows a save after rejection", async () => {
  let finish!: (value: {ok: boolean}) => void;
  const write = vi.fn().mockImplementationOnce(() => new Promise(done => {finish = done;})).mockResolvedValue({ok: true});
  const release = configureArtworkHost({read: async () => ({}), write});
  try {
    await loadArtwork();
    const first = saveGeneralArtwork({...DEFAULT_ARTWORK, positionX: 10});
    const second = saveGeneralArtwork({...DEFAULT_ARTWORK, positionX: 80});
    await vi.waitFor(() => expect(write).toHaveBeenCalledTimes(1));
    finish({ok: false});
    await expect(first).rejects.toThrow('save_failed');
    await second;
    expect(getGeneralArtwork().positionX).toBe(80);
    expect(write).toHaveBeenCalledTimes(2);
  } finally {release();}
});

describe("cover-owning theme", () => {
  it("is active only while some theme holds the bridge, and a release counts once", () => {
    expect(artworkThemeActive()).toBe(false);
    const release = artworkAccess.attach!();
    expect(artworkThemeActive()).toBe(true);
    release(); release();
    expect(artworkThemeActive()).toBe(false);
  });
});
