import { afterEach, describe, expect, it, vi } from "vitest";

import { createWindowsThemeStorage, STORAGE_SEED_TIMEOUT_MS, STORAGE_WRITE_TIMEOUT_MS } from "./storage";

afterEach(() => {
  vi.useRealTimers();
});

describe("Windows theme storage outbox", () => {
  it("waits for the companion's seed before answering a read", async () => {
    const storage = createWindowsThemeStorage();
    const read = storage.backend.get("hooandee-duo", "layout");
    expect(storage.status()).toEqual({ seeded: false, pending: 0 });
    storage.settle({ seed: { "hooandee-duo": { layout: "grid" } } });
    await expect(read).resolves.toEqual({ ok: true, value: "grid" });
    await expect(storage.backend.get("hooandee-bubble", "layout")).resolves.toEqual({ ok: true, value: null });
  });

  it("fails a read when the seed never arrives instead of answering empty", async () => {
    vi.useFakeTimers();
    const storage = createWindowsThemeStorage();
    const read = storage.backend.get("hooandee-duo", "layout");
    await vi.advanceTimersByTimeAsync(STORAGE_SEED_TIMEOUT_MS);
    await expect(read).resolves.toEqual({ ok: false, code: "unavailable" });
  });

  it("fails reads of a theme whose file the companion could not read", async () => {
    const storage = createWindowsThemeStorage();
    storage.settle({ seed: {}, unreadable: ["hooandee-duo"] });
    await expect(storage.backend.get("hooandee-duo", "layout")).resolves.toEqual({ ok: false, code: "read_failed" });
  });

  it("settles a write only once the companion persisted it", async () => {
    const storage = createWindowsThemeStorage();
    storage.settle({ seed: {} });
    let settled = false;
    const write = storage.backend.set("hooandee-duo", "groups", "[1]").then((result) => { settled = true; return result; });
    await Promise.resolve();
    expect(settled).toBe(false);
    await expect(storage.backend.get("hooandee-duo", "groups")).resolves.toEqual({ ok: true, value: "[1]" });
    const [taken] = storage.take();
    expect(taken).toMatchObject({ catalogId: "hooandee-duo", key: "groups", value: "[1]" });
    expect(storage.settle({ results: [{ seq: taken.seq, ok: true }] })).toEqual({ seeded: true, pending: 0 });
    await expect(write).resolves.toEqual({ ok: true });
    await expect(storage.backend.get("hooandee-duo", "groups")).resolves.toEqual({ ok: true, value: "[1]" });
  });

  it("reports a write the companion rejected or never took", async () => {
    vi.useFakeTimers();
    const storage = createWindowsThemeStorage();
    storage.settle({ seed: { "hooandee-duo": { groups: "old" } } });
    const rejected = storage.backend.set("hooandee-duo", "groups", "new");
    storage.settle({ results: [{ seq: storage.take()[0].seq, ok: false }] });
    await expect(rejected).resolves.toEqual({ ok: false, code: "write_failed" });
    await expect(storage.backend.get("hooandee-duo", "groups")).resolves.toEqual({ ok: true, value: "old" });

    const abandoned = storage.backend.set("hooandee-duo", "groups", "newer");
    await vi.advanceTimersByTimeAsync(STORAGE_WRITE_TIMEOUT_MS);
    await expect(abandoned).resolves.toEqual({ ok: false, code: "write_failed" });
    expect(storage.take()).toEqual([]);
  });

  it("fails everything pending when the host goes away", async () => {
    const storage = createWindowsThemeStorage();
    const read = storage.backend.get("hooandee-duo", "layout");
    const write = storage.backend.set("hooandee-duo", "layout", "grid");
    storage.dispose();
    await expect(read).resolves.toEqual({ ok: false, code: "unavailable" });
    await expect(write).resolves.toEqual({ ok: false, code: "write_failed" });
  });
});
