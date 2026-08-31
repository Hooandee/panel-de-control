// @vitest-environment happy-dom
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LOCAL_THEME_CATALOG } from "./catalog";
import type { CssLoaderReadySnapshot } from "./cssLoaderAdapter";
import type { CssLoaderSnapshot } from "./cssLoaderTypes";
import { ThemeInstallError } from "./panelThemeInstaller";
import type { ThemePublicationState } from "./remotePublication";
import { getThemesClient, useThemes, type ThemesDependencies } from "./useThemes";

const READY: CssLoaderReadySnapshot = {
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

type DependenciesOverrides = Omit<Partial<ThemesDependencies>, "adapter" | "activator" | "installer"> & {
  adapter?: Partial<ThemesDependencies["adapter"]>;
  activator?: Partial<ThemesDependencies["activator"]>;
  installer?: Partial<ThemesDependencies["installer"]>;
};

function dependencies(overrides: DependenciesOverrides = {}): ThemesDependencies {
  const base: ThemesDependencies = {
    catalog: LOCAL_THEME_CATALOG,
    adapter: {
      inspect: vi.fn(async () => structuredClone(READY)),
      requireReady: vi.fn(async () => structuredClone(READY) as CssLoaderSnapshot & { status: "ready" }),
      reloadTheme: vi.fn(async () => structuredClone(READY)),
      restoreThemeSnapshot: vi.fn(async () => structuredClone(READY) as CssLoaderSnapshot & { status: "ready" }),
      reconcileRecoveredThemes: vi.fn(async () => structuredClone(READY) as CssLoaderSnapshot & { status: "ready" }),
      setPatchValue: vi.fn(async () => structuredClone(READY)),
    },
    installer: {
      prepare: vi.fn(async () => ({
        themeId: "hooandee-gallery",
        themeName: "Hooandee Gallery",
        version: "0.7.8",
        transaction: "opaque-token",
      })),
      commit: vi.fn(async () => undefined),
      rollback: vi.fn(async () => undefined),
      pendingRecoveries: vi.fn(async () => []),
      acknowledgeRollback: vi.fn(async () => undefined),
    },
    activator: {
      activate: vi.fn(async () => structuredClone(READY)),
      deactivate: vi.fn(async () => structuredClone(READY)),
    },
  };
  return {
    ...base,
    ...overrides,
    adapter: { ...base.adapter, ...overrides.adapter },
    activator: { ...base.activator, ...overrides.activator },
    installer: { ...base.installer, ...overrides.installer },
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

  it("publishes local CSS Loader truth before a remote check finishes", async () => {
    const remote = deferred<ThemePublicationState>();
    const check = vi.fn(() => remote.promise);
    const deps = dependencies({ publication: { check } });
    const { result } = renderHook(() => useThemes(deps));

    await settle();

    expect(result.current.loading).toBe(false);
    expect(result.current.snapshot.status).toBe("ready");
    expect(result.current.publication.status).toBe("checking");
    expect(check).toHaveBeenCalledWith(READY, false);

    remote.resolve({
      status: "published",
      checkedAt: 100,
      themes: [{
        catalogId: "hooandee-gallery",
        cssLoaderName: "Hooandee Gallery",
        publishedVersion: "0.7.9",
        compatibility: "compatible",
        notes: { es: "Novedades" },
      }],
    });
    await settle();

    expect(result.current.publication.status).toBe("published");
    expect(result.current.cards.find((card) => card.id === "hooandee-gallery")).toMatchObject({
      publishedVersion: "0.7.9",
      preferredInstallSource: "bundled",
    });
  });

  it("keeps the local snapshot when remote discovery fails", async () => {
    const deps = dependencies({
      publication: {
        check: vi.fn(async () => ({
          status: "temporarily-unavailable",
          code: "offline",
          retryable: true,
        } satisfies ThemePublicationState)),
      },
    });
    const { result } = renderHook(() => useThemes(deps));

    await settle();

    expect(result.current.snapshot.status).toBe("ready");
    expect(result.current.error).toBeNull();
    expect(result.current.publication).toEqual({
      status: "temporarily-unavailable",
      code: "offline",
      retryable: true,
    });
  });

  it("retries a temporary publication failure before the success refresh window", async () => {
    let now = 1_000;
    vi.spyOn(Date, "now").mockImplementation(() => now);
    const check = vi.fn(async () => ({
      status: "temporarily-unavailable",
      code: "offline",
      retryable: true,
    } satisfies ThemePublicationState));
    const deps = dependencies({
      publication: { check },
      publicationRefreshIntervalMs: 15 * 60 * 1_000,
      publicationFailureRetryIntervalMs: 30_000,
    });
    const client = getThemesClient(deps);

    await client.refresh();
    await settle();
    expect(check).toHaveBeenCalledTimes(1);

    now += 29_999;
    await client.refresh();
    await settle();
    expect(check).toHaveBeenCalledTimes(1);

    now += 1;
    await client.refresh();
    await settle();
    expect(check).toHaveBeenCalledTimes(2);
  });

  it("reconciles a durable backend rollback before publishing the first snapshot", async () => {
    const recovery = {
      transaction: "opaque-token",
      themeName: "Hooandee Gallery",
      previousVersion: "v0.5.0",
    };
    const reconcileRecoveredThemes = vi.fn(async () => structuredClone(READY) as CssLoaderSnapshot & { status: "ready" });
    const acknowledgeRollback = vi.fn(async () => undefined);
    const inspect = vi.fn(async () => structuredClone(READY));
    const deps = dependencies({
      adapter: { inspect, reconcileRecoveredThemes },
      installer: {
        pendingRecoveries: vi.fn(async () => [recovery]),
        acknowledgeRollback,
      },
    });

    renderHook(() => useThemes(deps));
    await settle();

    expect(reconcileRecoveredThemes).toHaveBeenCalledWith([recovery], READY);
    expect(acknowledgeRollback).toHaveBeenCalledWith("opaque-token");
    expect(inspect).not.toHaveBeenCalled();
  });

  it("inspects CSS Loader when the durable recovery query fails", async () => {
    const inspect = vi.fn(async () => structuredClone(READY));
    const deps = dependencies({
      adapter: { inspect },
      installer: {
        pendingRecoveries: vi.fn(async () => { throw new Error("recovery unavailable"); }),
      },
    });

    const { result } = renderHook(() => useThemes(deps));
    await settle();

    expect(inspect).toHaveBeenCalledOnce();
    expect(result.current.snapshot.status).toBe("ready");
    expect(result.current.error).toBe("recovery unavailable");
  });

  it("blocks theme mutations when the durable journal cannot be recovered", async () => {
    const pendingRecoveries = vi.fn()
      .mockRejectedValueOnce(new ThemeInstallError(
        "invalid_journal",
        "Panel theme recovery is blocked",
      ))
      .mockResolvedValueOnce([]);
    const activate = vi.fn(async () => structuredClone(READY));
    const deps = dependencies({
      installer: { pendingRecoveries },
      activator: { activate },
    });
    const { result } = renderHook(() => useThemes(deps));
    await settle();

    expect(result.current.recoveryBlocked).toBe(true);
    await expect(result.current.activate("hooandee-obsidian-bloom")).resolves.toBe(false);
    expect(activate).not.toHaveBeenCalled();

    await act(async () => { await result.current.refresh(); });
    expect(result.current.recoveryBlocked).toBe(false);
    await act(async () => { await result.current.activate("hooandee-obsidian-bloom"); });
    expect(activate).toHaveBeenCalledOnce();
  });

  it("publishes an error state when neither recovery nor CSS Loader can be inspected", async () => {
    const deps = dependencies({
      adapter: {
        inspect: vi.fn(async () => { throw new Error("CSS Loader unavailable"); }),
      },
      installer: {
        pendingRecoveries: vi.fn(async () => { throw new Error("recovery unavailable"); }),
      },
    });

    const { result } = renderHook(() => useThemes(deps));
    await settle();

    expect(result.current.snapshot.status).toBe("error");
    expect(result.current.error).toBe("recovery unavailable");
  });

  it("shares one initial read and one operation lock across consumers", async () => {
    const activation = deferred<CssLoaderSnapshot>();
    const inspect = vi.fn(async () => structuredClone(READY));
    const activate = vi.fn(() => activation.promise);
    const deps = dependencies({
      adapter: { inspect, setPatchValue: vi.fn() },
      activator: { activate },
    });
    const { result } = renderHook(() => ({
      section: useThemes(deps),
      modal: useThemes(deps),
    }));
    await settle();

    expect(inspect).toHaveBeenCalledOnce();

    let first!: Promise<boolean>;
    let second!: Promise<boolean>;
    act(() => {
      first = result.current.section.activate("hooandee-obsidian-bloom");
      second = result.current.modal.activate("hooandee-gallery");
    });

    await expect(second).resolves.toBe(false);
    expect(activate).toHaveBeenCalledOnce();
    expect(result.current.section.operation).toEqual(result.current.modal.operation);

    activation.resolve(structuredClone(READY));
    await act(async () => { await first; });
  });

  it("does not let a manual refresh supersede a verified mutation", async () => {
    const activation = deferred<CssLoaderSnapshot>();
    const inspect = vi.fn(async () => structuredClone(READY));
    const deps = dependencies({
      adapter: { inspect, setPatchValue: vi.fn() },
      activator: { activate: vi.fn(() => activation.promise) },
    });
    const { result } = renderHook(() => useThemes(deps));
    await settle();

    let mutation!: Promise<boolean>;
    act(() => { mutation = result.current.activate("hooandee-obsidian-bloom"); });
    await act(async () => { await result.current.refresh(); });

    expect(inspect).toHaveBeenCalledOnce();
    activation.resolve(structuredClone(READY));
    await act(async () => { await mutation; });
    expect(result.current.operation).toBeNull();
  });

  it("refreshes again when the QAM remounts after every consumer left", async () => {
    const inspect = vi.fn(async () => structuredClone(READY));
    const deps = dependencies({
      adapter: { inspect, setPatchValue: vi.fn() },
    });
    const first = renderHook(() => useThemes(deps));
    await settle();
    first.unmount();

    const second = renderHook(() => useThemes(deps));
    await settle();

    expect(inspect).toHaveBeenCalledTimes(2);
    second.unmount();
  });

  it("reconciles external CSS Loader changes while mounted and stops polling after unmount", async () => {
    vi.useFakeTimers();
    try {
      const inspect = vi.fn()
        .mockResolvedValueOnce(structuredClone(READY))
        .mockResolvedValueOnce({ status: "missing", themes: [] } satisfies CssLoaderSnapshot);
      const deps = dependencies({
        refreshIntervalMs: 1_000,
        adapter: { inspect, setPatchValue: vi.fn() },
      });
      const rendered = renderHook(() => useThemes(deps));
      await settle();

      await act(async () => { await vi.advanceTimersByTimeAsync(1_000); });

      expect(inspect).toHaveBeenCalledTimes(2);
      expect(rendered.result.current.snapshot.status).toBe("missing");
      rendered.unmount();

      await vi.advanceTimersByTimeAsync(2_000);
      expect(inspect).toHaveBeenCalledTimes(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it("rechecks publication automatically after its frontend freshness window", async () => {
    vi.useFakeTimers();
    try {
      const check = vi.fn(async () => ({
        status: "published",
        checkedAt: 100,
        themes: [],
      } satisfies ThemePublicationState));
      const deps = dependencies({
        refreshIntervalMs: 1_000,
        publicationRefreshIntervalMs: 2_000,
        publication: { check },
      });
      const rendered = renderHook(() => useThemes(deps));
      await settle();

      expect(check).toHaveBeenCalledOnce();
      await act(async () => { await vi.advanceTimersByTimeAsync(1_000); });
      expect(check).toHaveBeenCalledOnce();
      await act(async () => { await vi.advanceTimersByTimeAsync(1_000); });
      expect(check).toHaveBeenCalledTimes(2);

      rendered.unmount();
    } finally {
      vi.useRealTimers();
    }
  });

  it("uses one polling authority and the shortest active consumer interval", async () => {
    vi.useFakeTimers();
    try {
      const inspect = vi.fn(async () => structuredClone(READY));
      const deps = dependencies({ adapter: { inspect } });
      const client = getThemesClient(deps);
      const releaseRuntime = client.subscribe(vi.fn(), 3_000);
      await client.refresh();

      const releaseUi = client.subscribe(vi.fn(), 1_000);
      await vi.advanceTimersByTimeAsync(999);
      expect(inspect).toHaveBeenCalledOnce();
      await vi.advanceTimersByTimeAsync(1);
      expect(inspect).toHaveBeenCalledTimes(2);

      releaseUi();
      await vi.advanceTimersByTimeAsync(2_999);
      expect(inspect).toHaveBeenCalledTimes(2);
      await vi.advanceTimersByTimeAsync(1);
      expect(inspect).toHaveBeenCalledTimes(3);
      releaseRuntime();
    } finally {
      vi.useRealTimers();
    }
  });

  it("clears loading when a verified mutation supersedes a slow refresh", async () => {
    const staleRead = deferred<CssLoaderSnapshot>();
    const inspect = vi.fn()
      .mockResolvedValueOnce(structuredClone(READY))
      .mockReturnValueOnce(staleRead.promise);
    const verified: CssLoaderSnapshot = {
      ...structuredClone(READY),
      themes: READY.themes.map((theme) => ({ ...theme, enabled: true })),
    };
    const deps = dependencies({
      adapter: { inspect, setPatchValue: vi.fn() },
      activator: { activate: vi.fn(async () => verified) },
    });
    const { result } = renderHook(() => useThemes(deps));
    await settle();

    act(() => { void result.current.refresh(); });
    await act(async () => {
      await result.current.activate("hooandee-obsidian-bloom");
    });

    expect(result.current.loading).toBe(false);
    expect(result.current.operation).toBeNull();
    expect(result.current.cards.find((card) => card.id === "hooandee-obsidian-bloom")?.active).toBe(true);

    staleRead.resolve({ status: "missing", themes: [] });
    await settle();
    expect(result.current.snapshot.status).toBe("ready");
  });

  it("reconciles CSS Loader readback when a mutation reports failure", async () => {
    const reconciled: CssLoaderSnapshot = {
      ...structuredClone(READY),
      themes: READY.themes.map((theme) => ({ ...theme, enabled: true })),
    };
    const inspect = vi.fn()
      .mockResolvedValueOnce(structuredClone(READY))
      .mockResolvedValueOnce(reconciled);
    const deps = dependencies({
      adapter: { inspect, setPatchValue: vi.fn() },
      activator: { activate: vi.fn(async () => { throw new Error("rollback failed"); }) },
    });
    const { result } = renderHook(() => useThemes(deps));
    await settle();

    let succeeded!: boolean;
    await act(async () => {
      succeeded = await result.current.activate("hooandee-obsidian-bloom");
    });

    expect(succeeded).toBe(false);
    expect(inspect).toHaveBeenCalledTimes(2);
    expect(result.current.cards.find((card) => card.id === "hooandee-obsidian-bloom")?.active).toBe(true);
    expect(result.current.error).toBe("rollback failed");
  });

  it("coalesces retry requests while a CSS Loader inspection is in flight", async () => {
    const read = deferred<CssLoaderSnapshot>();
    const inspect = vi.fn().mockReturnValue(read.promise);
    const deps = dependencies({ adapter: { inspect, setPatchValue: vi.fn() } });
    const { result } = renderHook(() => useThemes(deps));
    await settle();

    expect(result.current.refreshing).toBe(true);
    let firstRetry!: Promise<void>;
    let secondRetry!: Promise<void>;
    act(() => {
      firstRetry = result.current.refresh();
      secondRetry = result.current.refresh();
    });

    expect(firstRetry).toBe(secondRetry);
    expect(inspect).toHaveBeenCalledOnce();
    read.resolve(structuredClone(READY));
    await act(async () => { await firstRetry; });

    expect(result.current.snapshot.status).toBe("ready");
    expect(result.current.refreshing).toBe(false);
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
    const deps = dependencies({ adapter: { inspect: vi.fn(async () => READY), setPatchValue } });
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

  it("publishes a verified mutation through the shared client snapshot", async () => {
    const deps = dependencies();
    const client = getThemesClient(deps);
    const listener = vi.fn();
    const unsubscribe = client.subscribe(listener);
    await client.refresh();
    listener.mockClear();

    await client.setPatch("hooandee-obsidian-bloom", "Motion intensity", "Full");

    expect(listener).toHaveBeenCalled();
    expect(client.getSnapshot().snapshot.status).toBe("ready");
    unsubscribe();
  });

  it("settles safely when an initial read completes after unmount", async () => {
    const read = deferred<CssLoaderSnapshot>();
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    const deps = dependencies({
      adapter: { inspect: vi.fn(() => read.promise), setPatchValue: vi.fn() },
    });
    const rendered = renderHook(() => useThemes(deps));

    rendered.unmount();
    read.resolve(structuredClone(READY));
    await act(async () => { await read.promise; });

    expect(error).not.toHaveBeenCalled();
  });

  it("blocks duplicate installs and publishes only CSS Loader's exact verified version", async () => {
    const reload = deferred<CssLoaderReadySnapshot>();
    const reloadTheme = vi.fn(() => reload.promise);
    const prepare = vi.fn(async () => ({
      themeId: "hooandee-gallery",
      themeName: "Hooandee Gallery",
      version: "0.7.8",
      transaction: "opaque-token",
    }));
    const commit = vi.fn(async () => undefined);
    const deps = dependencies({
      adapter: { inspect: vi.fn(async () => READY), reloadTheme },
      installer: { prepare, commit },
    });
    const { result } = renderHook(() => useThemes(deps));
    await settle();

    let first!: Promise<boolean>;
    let second!: Promise<boolean>;
    act(() => {
      first = result.current.install("hooandee-gallery");
      second = result.current.install("hooandee-gallery");
    });

    await expect(second).resolves.toBe(false);
    expect(prepare).toHaveBeenCalledWith({ kind: "bundled", packageId: "hooandee-gallery" });
    expect(reloadTheme).toHaveBeenCalledWith("Hooandee Gallery", "0.7.8", READY);
    reload.resolve(structuredClone(READY));
    await act(async () => { await first; });
    expect(commit).toHaveBeenCalledWith("opaque-token");
    expect(result.current.operation).toBeNull();
  });

  it("freezes the published version when preparing an official update", async () => {
    const galleryReady: CssLoaderReadySnapshot = {
      ...READY,
      themes: [{
        id: "Hooandee Gallery",
        name: "Hooandee Gallery",
        displayName: "Hooandee Gallery",
        version: "0.7.8",
        author: "Hooandee",
        enabled: true,
        patches: [],
      }],
    };
    const prepare = vi.fn(async () => ({
      themeId: "hooandee-gallery",
      themeName: "Hooandee Gallery",
      version: "0.7.9",
      transaction: "remote-token",
    }));
    const reloadTheme = vi.fn(async () => ({
      ...galleryReady,
      themes: galleryReady.themes.map((theme) => ({ ...theme, version: "0.7.9" })),
    }));
    const deps = dependencies({
      adapter: {
        inspect: vi.fn(async () => galleryReady),
        requireReady: vi.fn(async () => galleryReady),
        reloadTheme,
      },
      publication: {
        check: vi.fn(async () => ({
          status: "published",
          checkedAt: 100,
          themes: [{
            catalogId: "hooandee-gallery",
            cssLoaderName: "Hooandee Gallery",
            publishedVersion: "0.7.9",
            compatibility: "compatible",
            notes: {},
          }],
        } satisfies ThemePublicationState)),
      },
      installer: { prepare },
    });
    const { result } = renderHook(() => useThemes(deps));
    await settle();

    await act(async () => { await result.current.install("hooandee-gallery"); });

    expect(prepare).toHaveBeenCalledWith({
      kind: "official-remote",
      channelId: "panel-pages-v1",
      catalogId: "hooandee-gallery",
      expectedVersion: "0.7.9",
    });
    expect(reloadTheme).toHaveBeenCalledWith("Hooandee Gallery", "0.7.9", galleryReady);
  });

  it("rolls back the filesystem and verifies CSS Loader's original snapshot when reload fails", async () => {
    const reloadError = new Error("reset failed");
    const rollback = vi.fn(async () => undefined);
    const acknowledgeRollback = vi.fn(async () => undefined);
    const restoreThemeSnapshot = vi.fn(async () => structuredClone(READY) as CssLoaderSnapshot & { status: "ready" });
    const deps = dependencies({
      adapter: {
        inspect: vi.fn(async () => READY),
        reloadTheme: vi.fn(async () => { throw reloadError; }),
        restoreThemeSnapshot,
      },
      installer: { rollback, acknowledgeRollback },
    });
    const { result } = renderHook(() => useThemes(deps));
    await settle();

    let succeeded!: boolean;
    await act(async () => { succeeded = await result.current.install("hooandee-gallery"); });

    expect(succeeded).toBe(false);
    expect(rollback).toHaveBeenCalledWith("opaque-token");
    expect(restoreThemeSnapshot).toHaveBeenCalledWith(READY);
    expect(acknowledgeRollback).toHaveBeenCalledWith("opaque-token");
    expect(result.current.error).toBe("reset failed");
  });

  it("treats a failed rollback as the primary recoverable installation error", async () => {
    const deps = dependencies({
      adapter: {
        inspect: vi.fn(async () => READY),
        reloadTheme: vi.fn(async () => { throw new Error("reset failed"); }),
      },
      installer: {
        rollback: vi.fn(async () => { throw new Error("backup unavailable"); }),
      },
    });
    const { result } = renderHook(() => useThemes(deps));
    await settle();

    await act(async () => { await result.current.install("hooandee-gallery"); });

    expect(result.current.error).toContain("backup unavailable");
    expect(result.current.recoveryBlocked).toBe(true);
  });

  it("rolls back a prepared package whose identity contradicts the catalog", async () => {
    const rollback = vi.fn(async () => undefined);
    const reloadTheme = vi.fn();
    const deps = dependencies({
      adapter: { inspect: vi.fn(async () => READY), reloadTheme },
      installer: {
        prepare: vi.fn(async () => ({
          themeId: "hooandee-gallery",
          themeName: "Wrong Theme",
          version: "0.6.0",
          transaction: "opaque-token",
        })),
        rollback,
      },
    });
    const { result } = renderHook(() => useThemes(deps));
    await settle();

    await act(async () => { await result.current.install("hooandee-gallery"); });

    expect(rollback).toHaveBeenCalledWith("opaque-token");
    expect(reloadTheme).not.toHaveBeenCalled();
    expect(result.current.error).toContain("does not match the catalog");
  });

  it("rechecks durable recovery when prepare fails before returning its token", async () => {
    const pendingRecoveries = vi.fn(async () => []);
    const deps = dependencies({
      adapter: { inspect: vi.fn(async () => READY) },
      installer: {
        pendingRecoveries,
        prepare: vi.fn(async () => { throw new Error("journal transition failed"); }),
      },
    });
    const { result } = renderHook(() => useThemes(deps));
    await settle();

    await act(async () => { await result.current.install("hooandee-gallery"); });
    await act(async () => { await result.current.refresh(); });

    expect(pendingRecoveries).toHaveBeenCalledTimes(2);
  });

  it("serializes durable recovery with every theme mutation", async () => {
    const recovery = deferred<readonly []>();
    const pendingRecoveries = vi.fn()
      .mockResolvedValueOnce([])
      .mockReturnValueOnce(recovery.promise);
    const activate = vi.fn(async () => structuredClone(READY));
    const deps = dependencies({
      adapter: { inspect: vi.fn(async () => READY) },
      installer: {
        pendingRecoveries,
        prepare: vi.fn(async () => { throw new Error("journal transition failed"); }),
      },
      activator: { activate },
    });
    const { result } = renderHook(() => useThemes(deps));
    await settle();
    await act(async () => { await result.current.install("hooandee-gallery"); });

    act(() => { void result.current.refresh(); });

    expect(result.current.operation).toEqual({ kind: "recovering" });
    await expect(result.current.activate("hooandee-obsidian-bloom")).resolves.toBe(false);
    expect(activate).not.toHaveBeenCalled();

    recovery.resolve([]);
    await settle();
    expect(result.current.operation).toBeNull();
  });

  it("retries an unresolved recovery boundary before a later mutation", async () => {
    const pendingRecoveries = vi.fn()
      .mockRejectedValueOnce(new Error("recovery unavailable"))
      .mockResolvedValueOnce([]);
    const activate = vi.fn(async () => structuredClone(READY));
    const deps = dependencies({
      adapter: { inspect: vi.fn(async () => READY) },
      installer: { pendingRecoveries },
      activator: { activate },
    });
    const { result } = renderHook(() => useThemes(deps));
    await settle();

    await act(async () => { await result.current.activate("hooandee-obsidian-bloom"); });

    expect(pendingRecoveries).toHaveBeenCalledTimes(2);
    expect(activate).toHaveBeenCalledOnce();
  });
});
