// @vitest-environment happy-dom
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LOCAL_THEME_CATALOG } from "./catalog";
import type { CssLoaderSnapshot } from "./cssLoaderTypes";
import { useThemes, type ThemesDependencies } from "./useThemes";

const READY: CssLoaderSnapshot = {
  status: "ready",
  pluginVersion: "2.1.2",
  backendVersion: 9,
  themes: [{
    id: "Hooandee Obsidian Bloom",
    name: "Hooandee Obsidian Bloom",
    displayName: "Obsidian Bloom",
    version: "0.1.0",
    author: "Hooandee",
    enabled: false,
    patches: [],
  }],
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function dependencies(overrides: Partial<ThemesDependencies> = {}): ThemesDependencies {
  return {
    catalog: LOCAL_THEME_CATALOG,
    adapter: {
      inspect: vi.fn(async () => structuredClone(READY)),
      setPatchValue: vi.fn(async () => structuredClone(READY)),
      installTheme: vi.fn(async () => structuredClone(READY)),
    },
    activator: {
      activate: vi.fn(async () => structuredClone(READY)),
    },
    ...overrides,
  };
}

async function settle() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("useThemes", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads a verified snapshot and derives catalog cards", async () => {
    const deps = dependencies();
    const { result } = renderHook(() => useThemes(deps));

    await settle();

    expect(result.current.loading).toBe(false);
    expect(result.current.snapshot.status).toBe("ready");
    expect(result.current.cards.find((card) => card.id === "hooandee-obsidian-bloom")).toMatchObject({
      installed: true,
      active: false,
    });
  });

  it("ignores an older refresh that settles after a newer request", async () => {
    const first = deferred<CssLoaderSnapshot>();
    const second = deferred<CssLoaderSnapshot>();
    const inspect = vi.fn()
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    const deps = dependencies({ adapter: { inspect, setPatchValue: vi.fn(), installTheme: vi.fn() } });
    const { result } = renderHook(() => useThemes(deps));

    let latest!: Promise<void>;
    act(() => { latest = result.current.refresh(); });
    second.resolve(structuredClone(READY));
    await act(async () => { await latest; });
    first.resolve({ status: "missing", themes: [] });
    await settle();

    expect(result.current.snapshot.status).toBe("ready");
  });

  it("blocks a second activation until the first finishes", async () => {
    const activation = deferred<CssLoaderSnapshot>();
    const activate = vi.fn(() => activation.promise);
    const deps = dependencies({ activator: { activate } });
    const { result } = renderHook(() => useThemes(deps));
    await settle();

    let first!: Promise<boolean>;
    let second!: Promise<boolean>;
    act(() => {
      first = result.current.activate("hooandee-obsidian-bloom");
      second = result.current.activate("hooandee-gallery");
    });

    await expect(second).resolves.toBe(false);
    expect(activate).toHaveBeenCalledOnce();
    expect(result.current.operation).toEqual({
      kind: "activating",
      themeId: "hooandee-obsidian-bloom",
    });

    activation.resolve(structuredClone(READY));
    await act(async () => { await first; });
    expect(result.current.operation).toBeNull();
  });

  it("blocks duplicate patch writes and publishes the verified result", async () => {
    const write = deferred<CssLoaderSnapshot>();
    const setPatchValue = vi.fn(() => write.promise);
    const deps = dependencies({ adapter: { inspect: vi.fn(async () => READY), setPatchValue, installTheme: vi.fn() } });
    const { result } = renderHook(() => useThemes(deps));
    await settle();

    let first!: Promise<boolean>;
    let second!: Promise<boolean>;
    act(() => {
      first = result.current.setPatch("hooandee-obsidian-bloom", "Motion intensity", "Full");
      second = result.current.setPatch("hooandee-obsidian-bloom", "Motion intensity", "Reduced");
    });

    await expect(second).resolves.toBe(false);
    expect(setPatchValue).toHaveBeenCalledOnce();
    write.resolve(structuredClone(READY));
    await act(async () => { await first; });
    expect(result.current.operation).toBeNull();
  });

  it("signals the runtime immediately after a verified patch write", async () => {
    const notifyRuntime = vi.fn();
    const deps = dependencies({ notifyRuntime });
    const { result } = renderHook(() => useThemes(deps));
    await settle();

    await act(async () => {
      await result.current.setPatch("hooandee-obsidian-bloom", "Motion intensity", "Full");
    });

    expect(notifyRuntime).toHaveBeenCalledOnce();
  });

  it("signals the runtime immediately after a verified activation", async () => {
    const notifyRuntime = vi.fn();
    const deps = dependencies({ notifyRuntime });
    const { result } = renderHook(() => useThemes(deps));
    await settle();

    await act(async () => {
      await result.current.activate("hooandee-obsidian-bloom");
    });

    expect(notifyRuntime).toHaveBeenCalledOnce();
  });

  it("settles safely when an initial read completes after unmount", async () => {
    const read = deferred<CssLoaderSnapshot>();
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    const deps = dependencies({
      adapter: { inspect: vi.fn(() => read.promise), setPatchValue: vi.fn(), installTheme: vi.fn() },
    });
    const rendered = renderHook(() => useThemes(deps));

    rendered.unmount();
    read.resolve(structuredClone(READY));
    await act(async () => { await read.promise; });

    expect(error).not.toHaveBeenCalled();
  });

  it("blocks duplicate installs and publishes only CSS Loader's verified result", async () => {
    const catalog: ThemesDependencies["catalog"] = {
      ...LOCAL_THEME_CATALOG,
      themes: LOCAL_THEME_CATALOG.themes.map((entry) => entry.id === "hooandee-obsidian-bloom"
        ? {
            ...entry,
            installSource: {
              kind: "css-loader-api" as const,
              themeId: "obsidian-bloom",
              baseUrl: "https://themes.hooandee.example/v1/",
            },
          }
        : entry),
    };
    const install = deferred<CssLoaderSnapshot>();
    const installTheme = vi.fn(() => install.promise);
    const deps = dependencies({
      catalog,
      adapter: { inspect: vi.fn(async () => READY), setPatchValue: vi.fn(), installTheme },
    });
    const { result } = renderHook(() => useThemes(deps));
    await settle();

    let first!: Promise<boolean>;
    let second!: Promise<boolean>;
    act(() => {
      first = result.current.install("hooandee-obsidian-bloom");
      second = result.current.install("hooandee-obsidian-bloom");
    });

    await expect(second).resolves.toBe(false);
    expect(installTheme).toHaveBeenCalledOnce();
    install.resolve(structuredClone(READY));
    await act(async () => { await first; });
    expect(result.current.operation).toBeNull();
  });
});
