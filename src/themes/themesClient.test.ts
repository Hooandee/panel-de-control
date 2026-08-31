import { describe, expect, it, vi } from "vitest";

import type { CssLoaderReadySnapshot } from "./cssLoaderAdapter";
import type { PublishedThemeRelease, ThemePublicationState } from "./remotePublication";
import { ThemesClient, type ThemesDependencies } from "./themesClient";

const RELEASE: PublishedThemeRelease = {
  catalogId: "example-theme",
  cssLoaderName: "Example Theme",
  publishedVersion: "1.2.3",
  displayName: { es: "Tema", en: "Example Theme", it: "Tema" },
  description: { es: "Descripcion", en: "Description", it: "Descrizione" },
  author: "Example Author",
  tags: [],
  notes: {},
  compatibility: "compatible",
  exclusiveGroup: "interface",
};
const PUBLICATION: ThemePublicationState = { status: "published", checkedAt: 10, themes: [RELEASE] };
const READY: CssLoaderReadySnapshot = {
  status: "ready", pluginVersion: "2.1.2", backendVersion: 9, themes: [],
};

function dependencies(overrides: Partial<ThemesDependencies> = {}): ThemesDependencies {
  const base: ThemesDependencies = {
    adapter: {
      inspect: vi.fn(async () => READY),
      requireReady: vi.fn(async () => READY),
      reloadTheme: vi.fn(async () => READY),
      restoreThemeSnapshot: vi.fn(async () => READY),
      reconcileRecoveredThemes: vi.fn(async () => READY),
      setPatchValue: vi.fn(async () => READY),
    },
    installer: {
      prepare: vi.fn(async () => ({
        themeId: "example-theme", themeName: "Example Theme", version: "1.2.3", transaction: "token",
      })),
      commit: vi.fn(async () => undefined),
      rollback: vi.fn(async () => undefined),
      pendingRecoveries: vi.fn(async () => []),
      acknowledgeRollback: vi.fn(async () => undefined),
    },
    activator: {
      activate: vi.fn(async () => READY),
      deactivate: vi.fn(async () => READY),
    },
    publication: { check: vi.fn(async () => PUBLICATION) },
  };
  return { ...base, ...overrides };
}

describe("ThemesClient", () => {
  it("starts and deduplicates publication discovery even when CSS Loader is missing", async () => {
    let resolve!: (value: ThemePublicationState) => void;
    const check = vi.fn(() => new Promise<ThemePublicationState>((done) => { resolve = done; }));
    const deps = dependencies({
      adapter: { ...dependencies().adapter, inspect: vi.fn(async () => ({ status: "missing" as const, themes: [] })) },
      publication: { check },
    });
    const client = new ThemesClient(deps);

    const first = client.refresh();
    const second = client.refreshPublication();
    await Promise.resolve();
    expect(check).toHaveBeenCalledOnce();
    expect(check).toHaveBeenCalledWith(false);
    resolve(PUBLICATION);
    await Promise.all([first, second]);
    expect(client.getSnapshot().publication).toEqual(PUBLICATION);
  });

  it("installs through the official channel using only the confirmed version", async () => {
    const deps = dependencies();
    const client = new ThemesClient(deps);
    await client.refresh();

    await expect(client.install("example-theme", { version: "1.2.3" })).resolves.toBe(true);
    expect(deps.installer.prepare).toHaveBeenCalledWith({
      kind: "official-remote", channelId: "panel-pages-v1", catalogId: "example-theme", expectedVersion: "1.2.3",
    });
  });

  it("passes the current cached publication to activation", async () => {
    const cached: ThemePublicationState = {
      status: "cached", checkedAt: 10, themes: [RELEASE], code: "offline", retryable: true,
    };
    const activate = vi.fn(async () => READY);
    const deps = dependencies({ publication: { check: vi.fn(async () => cached) }, activator: { activate, deactivate: vi.fn() } });
    const client = new ThemesClient(deps);
    await client.refresh();

    await expect(client.activate("example-theme")).resolves.toBe(true);
    expect(activate).toHaveBeenCalledWith("example-theme", [RELEASE]);
  });

  it("blocks install and activation honestly when CSS Loader is not ready", async () => {
    const deps = dependencies({
      adapter: { ...dependencies().adapter, inspect: vi.fn(async () => ({ status: "disabled" as const, themes: [] })) },
    });
    const client = new ThemesClient(deps);
    await client.refresh();

    await expect(client.install("example-theme", { version: "1.2.3" })).resolves.toBe(false);
    await expect(client.activate("example-theme")).resolves.toBe(false);
    expect(deps.installer.prepare).not.toHaveBeenCalled();
    expect(deps.activator.activate).not.toHaveBeenCalled();
  });
});
