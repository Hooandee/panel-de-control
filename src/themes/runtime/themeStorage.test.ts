import { describe, expect, it, vi } from "vitest";

import { createThemeStorage, THEME_STORAGE_MAX_VALUE_BYTES, ThemeStorageError } from "./themeStorage";

function memoryBackend() {
  const files = new Map<string, Map<string, string>>();
  return {
    files,
    get: vi.fn(async (catalogId: string, key: string) => ({ ok: true, value: files.get(catalogId)?.get(key) ?? null })),
    set: vi.fn(async (catalogId: string, key: string, value: string) => {
      const values = files.get(catalogId) ?? new Map<string, string>();
      values.set(key, value);
      files.set(catalogId, values);
      return { ok: true };
    }),
  };
}

describe("theme storage", () => {
  it("reads back what a theme wrote", async () => {
    const storage = createThemeStorage(memoryBackend()).forTheme("hooandee-duo");
    expect(await storage.get("pdc.hybrid.dock.v1")).toBeNull();
    expect(await storage.set("pdc.hybrid.dock.v1", "{\"size\":3}")).toBe(true);
    expect(await storage.get("pdc.hybrid.dock.v1")).toBe("{\"size\":3}");
  });

  it("keeps each theme to its own values", async () => {
    const provider = createThemeStorage(memoryBackend());
    await provider.forTheme("hooandee-duo").set("layout", "duo");
    await provider.forTheme("hooandee-bubble").set("layout", "bubble");
    expect(await provider.forTheme("hooandee-duo").get("layout")).toBe("duo");
    expect(await provider.forTheme("hooandee-bubble").get("layout")).toBe("bubble");
    expect(await provider.forTheme("hooandee-eclipse").get("layout")).toBeNull();
  });

  it("refuses an oversized value without calling the backend", async () => {
    const backend = memoryBackend();
    const storage = createThemeStorage(backend).forTheme("hooandee-duo");
    expect(await storage.set("groups", "x".repeat(THEME_STORAGE_MAX_VALUE_BYTES + 1))).toBe(false);
    expect(await storage.set("groups", "é".repeat(THEME_STORAGE_MAX_VALUE_BYTES / 2 + 1))).toBe(false);
    expect(await storage.set("../escape", "x")).toBe(false);
    expect(backend.set).not.toHaveBeenCalled();
  });

  it("reports a backend rejection as a failed save", async () => {
    const storage = createThemeStorage({
      get: async () => ({ ok: true, value: null }),
      set: async () => ({ ok: false, code: "too_large" }),
    }).forTheme("hooandee-duo");
    expect(await storage.set("groups", "x")).toBe(false);
  });

  it("never reports a failed read as an empty value", async () => {
    const failing = createThemeStorage({
      get: async () => ({ ok: false, code: "corrupt" }),
      set: async () => ({ ok: true }),
    }).forTheme("hooandee-duo");
    await expect(failing.get("groups")).rejects.toMatchObject({ code: "corrupt" });

    const throwing = createThemeStorage({
      get: async () => { throw new Error("backend gone"); },
      set: async () => { throw new Error("backend gone"); },
    }).forTheme("hooandee-duo");
    await expect(throwing.get("groups")).rejects.toThrow("backend gone");
    expect(await throwing.set("groups", "x")).toBe(false);

    const malformed = createThemeStorage({
      get: async () => ({ ok: true, value: 3 }),
      set: async () => ({ ok: true }),
    }).forTheme("hooandee-duo");
    await expect(malformed.get("groups")).rejects.toBeInstanceOf(ThemeStorageError);
    await expect(malformed.get("bad key")).rejects.toMatchObject({ code: "invalid_key" });
  });

  it("applies a theme's calls in the order it made them", async () => {
    const order: string[] = [];
    let release!: () => void;
    const gate = new Promise<void>((resolve) => { release = resolve; });
    const storage = createThemeStorage({
      get: async (_id, key) => { order.push(`get:${key}`); return { ok: true, value: null }; },
      set: async (_id, key, value) => {
        if (value === "first") await gate;
        order.push(`set:${key}=${value}`);
        return { ok: true };
      },
    }).forTheme("hooandee-duo");
    const first = storage.set("a", "first");
    const second = storage.set("a", "second");
    const read = storage.get("a");
    release();
    await Promise.all([first, second, read]);
    expect(order).toEqual(["set:a=first", "set:a=second", "get:a"]);
  });
});
