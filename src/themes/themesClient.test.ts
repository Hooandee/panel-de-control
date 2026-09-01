import { describe, expect, it, vi } from "vitest";

import { ThemeActivationError, ThemeActivator, type ThemeActivationAdapter } from "./activation";
import type { CssLoaderReadySnapshot } from "./cssLoaderAdapter";
import type { CssLoaderTheme } from "./cssLoaderTypes";
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
    const order: string[] = [];
    deps.adapter.requireReady = vi.fn(async () => {
      order.push("snapshot");
      return READY;
    });
    deps.installer.prepare = vi.fn(async () => {
      order.push("prepare");
      return {
        themeId: "example-theme", themeName: "Example Theme", version: "1.2.3", transaction: "token",
      };
    });
    deps.adapter.reloadTheme = vi.fn(async () => {
      order.push("reload");
      return READY;
    });
    deps.installer.commit = vi.fn(async () => {
      order.push("commit");
    });
    const client = new ThemesClient(deps);
    await client.refresh();

    await expect(client.install("example-theme", { version: "1.2.3" })).resolves.toBe(true);
    expect(deps.installer.prepare).toHaveBeenCalledWith({
      kind: "official-remote", channelId: "panel-pages-v1", catalogId: "example-theme", expectedVersion: "1.2.3",
    });
    expect(order).toEqual(["snapshot", "prepare", "reload", "commit"]);
    expect(deps.adapter.reloadTheme).toHaveBeenCalledWith("Example Theme", "1.2.3", READY);
    expect(deps.installer.commit).toHaveBeenCalledWith("token");
    expect(deps.installer.rollback).not.toHaveBeenCalled();
    expect(deps.installer.acknowledgeRollback).not.toHaveBeenCalled();
  });

  it.each(["reload", "commit"] as const)(
    "rolls back, restores, and acknowledges when %s fails",
    async (failure) => {
      const deps = dependencies();
      const order: string[] = [];
      deps.adapter.requireReady = vi.fn(async () => {
        order.push("snapshot");
        return READY;
      });
      deps.installer.prepare = vi.fn(async () => {
        order.push("prepare");
        return {
          themeId: "example-theme", themeName: "Example Theme", version: "1.2.3", transaction: "token",
        };
      });
      deps.adapter.reloadTheme = vi.fn(async () => {
        order.push("reload");
        if (failure === "reload") throw new Error("reload failed");
        return READY;
      });
      deps.installer.commit = vi.fn(async () => {
        order.push("commit");
        if (failure === "commit") throw new Error("commit failed");
      });
      deps.installer.rollback = vi.fn(async () => {
        order.push("rollback");
      });
      deps.adapter.restoreThemeSnapshot = vi.fn(async () => {
        order.push("restore");
        return READY;
      });
      deps.installer.acknowledgeRollback = vi.fn(async () => {
        order.push("acknowledge");
      });
      const client = new ThemesClient(deps);
      await client.refresh();

      await expect(client.install("example-theme", { version: "1.2.3" })).resolves.toBe(false);

      expect(order).toEqual([
        "snapshot",
        "prepare",
        "reload",
        ...(failure === "commit" ? ["commit"] : []),
        "rollback",
        "restore",
        "acknowledge",
      ]);
      expect(client.getSnapshot()).toMatchObject({ recoveryBlocked: false });
    },
  );

  it("keeps recovery blocked and unacknowledged when snapshot restoration fails", async () => {
    const deps = dependencies();
    deps.adapter.reloadTheme = vi.fn(async () => { throw new Error("reload failed"); });
    deps.adapter.restoreThemeSnapshot = vi.fn(async () => { throw new Error("restore failed"); });
    const client = new ThemesClient(deps);
    await client.refresh();

    await expect(client.install("example-theme", { version: "1.2.3" })).resolves.toBe(false);

    expect(deps.installer.rollback).toHaveBeenCalledWith("token");
    expect(deps.installer.acknowledgeRollback).not.toHaveBeenCalled();
    expect(client.getSnapshot()).toMatchObject({
      recoveryBlocked: true,
      error: expect.stringContaining("Theme rollback could not be verified"),
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

  it("keeps mutations blocked until activation recovery is verified", async () => {
    let recovery: "none" | "pending" | "ready" = "none";
    const activator = {
      activate: vi.fn(async () => {
        recovery = "pending";
        throw new ThemeActivationError("rollback_failed", "waiting for CSS Loader", true);
      }),
      deactivate: vi.fn(async () => READY),
      reconcilePendingRecovery: vi.fn(async () => {
        if (recovery === "pending") {
          throw new ThemeActivationError("rollback_failed", "still recovering", true);
        }
        if (recovery === "ready") {
          recovery = "none";
          return READY;
        }
        return null;
      }),
    };
    const client = new ThemesClient(dependencies({ activator }));
    await client.refresh();

    await expect(client.activate("example-theme")).resolves.toBe(false);
    expect(client.getSnapshot().recoveryBlocked).toBe(true);
    await expect(client.install("example-theme", { version: "1.2.3" })).resolves.toBe(false);

    await client.refresh();
    expect(client.getSnapshot().recoveryBlocked).toBe(true);
    recovery = "ready";
    await client.refresh();
    expect(client.getSnapshot()).toMatchObject({ recoveryBlocked: false, error: null });
  });

  it("retries a rejected activation restore without clearing the recovery block early", async () => {
    const themes: CssLoaderTheme[] = [{
      id: "Example Theme",
      name: "Example Theme",
      displayName: "Example Theme",
      version: "1.2.3",
      author: "Example Author",
      enabled: false,
      patches: [{
        name: "Color",
        defaultValue: "Blue",
        value: "Red",
        options: ["Blue", "Red"],
        type: "dropdown",
        rawType: "dropdown",
      }],
    }];
    let restoreAttempts = 0;
    const activationAdapter: ThemeActivationAdapter = {
      inspect: async () => ({
        status: "ready",
        pluginVersion: "2.1.2",
        backendVersion: 9,
        themes: structuredClone(themes),
      }),
      setThemeState: async (_name, enabled) => {
        themes[0].enabled = enabled;
        themes[0].patches[0].value = "Blue";
        return activationAdapter.inspect();
      },
      restoreThemeSnapshot: async (expected) => {
        restoreAttempts += 1;
        if (restoreAttempts < 3) throw new Error("CSS Loader unavailable");
        themes.splice(0, themes.length, ...structuredClone(expected.themes));
        return activationAdapter.inspect() as Promise<CssLoaderReadySnapshot>;
      },
      hasPendingMutation: () => false,
      waitForPendingMutation: async () => undefined,
    };
    const deps = dependencies({ activator: new ThemeActivator(activationAdapter) });
    const client = new ThemesClient(deps);
    await client.refresh();

    await expect(client.activate("example-theme")).resolves.toBe(false);
    expect(client.getSnapshot().recoveryBlocked).toBe(true);
    expect(restoreAttempts).toBe(1);

    await client.refresh();
    expect(client.getSnapshot().recoveryBlocked).toBe(true);
    expect(restoreAttempts).toBe(2);

    await client.refresh();
    expect(client.getSnapshot()).toMatchObject({
      recoveryBlocked: false,
      error: null,
      snapshot: { status: "ready" },
    });
    expect(restoreAttempts).toBe(3);
    expect(themes[0]).toMatchObject({
      enabled: false,
      patches: [expect.objectContaining({ value: "Red" })],
    });
  });

  it("rejects activation of an incompatible catalog release without blocking deactivation", async () => {
    const incompatibleRelease: PublishedThemeRelease = {
      ...RELEASE,
      compatibility: "incompatible-panel",
    };
    const publication: ThemePublicationState = {
      status: "published",
      checkedAt: 10,
      themes: [incompatibleRelease],
    };
    const activate = vi.fn(async () => READY);
    const deactivate = vi.fn(async () => READY);
    const deps = dependencies({
      publication: { check: vi.fn(async () => publication) },
      activator: { activate, deactivate },
    });
    const client = new ThemesClient(deps);
    await client.refresh();

    await expect(client.activate("example-theme")).resolves.toBe(false);
    await expect(client.deactivate("example-theme")).resolves.toBe(true);
    expect(activate).not.toHaveBeenCalled();
    expect(deactivate).toHaveBeenCalledWith("example-theme", [incompatibleRelease]);
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
