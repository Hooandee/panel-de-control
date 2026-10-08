import { describe, expect, it, vi } from "vitest";

import { ThemeActivationError, ThemeActivator, type ThemeActivationAdapter } from "./activation";
import { CssLoaderOperationError, type CssLoaderReadySnapshot } from "./cssLoaderAdapter";
import type { CssLoaderTheme } from "./cssLoaderTypes";
import type { PublishedThemeRelease, ThemePublicationState } from "./remotePublication";
import { ThemeInstallError } from "./panelThemeInstaller";
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
  status: "ready", themes: [],
};
const INSTALLED_THEME: CssLoaderTheme = {
  id: "Example Theme",
  name: "Example Theme",
  displayName: "Example Theme",
  version: "1.2.3",
  author: "Example Author",
  enabled: true,
  patches: [],
};
const INSTALLED_READY: CssLoaderReadySnapshot = {
  ...READY,
  themes: [INSTALLED_THEME],
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
      deleteTheme: vi.fn(async () => READY),
    },
    installer: {
      prepare: vi.fn(async () => ({
        themeId: "example-theme", themeName: "Example Theme", version: "1.2.3", transaction: "token",
      })),
      commit: vi.fn(async () => undefined),
      discardReceipt: vi.fn(async () => undefined),
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
  it("publishes the confirmed snapshot after uninstalling a catalog theme", async () => {
    const deps = dependencies();
    deps.adapter.inspect = vi.fn(async () => INSTALLED_READY);
    deps.adapter.deleteTheme = vi.fn(async () => READY);
    const client = new ThemesClient(deps);
    await client.refresh();

    await expect(client.uninstall("example-theme")).resolves.toBe(true);

    expect(client.getSnapshot()).toMatchObject({
      snapshot: READY,
      operation: null,
      error: null,
    });
    expect(deps.adapter.deleteTheme).toHaveBeenCalledWith("Example Theme");
    expect(deps.installer.discardReceipt).toHaveBeenCalledWith("example-theme");
  });

  it("waits for CSS Loader confirmation before discarding the exact receipt", async () => {
    let confirmDeletion!: (snapshot: CssLoaderReadySnapshot) => void;
    const order: string[] = [];
    const deps = dependencies();
    deps.adapter.inspect = vi.fn(async () => INSTALLED_READY);
    deps.adapter.deleteTheme = vi.fn(() => {
      order.push("delete");
      return new Promise<CssLoaderReadySnapshot>((done) => { confirmDeletion = done; });
    });
    deps.installer.discardReceipt = vi.fn(async () => { order.push("discard"); });
    const client = new ThemesClient(deps);
    await client.refresh();

    const uninstalling = client.uninstall("example-theme");
    await vi.waitFor(() => expect(order).toEqual(["delete"]));

    expect(deps.installer.discardReceipt).not.toHaveBeenCalled();
    confirmDeletion(READY);
    await expect(uninstalling).resolves.toBe(true);
    expect(order).toEqual(["delete", "discard"]);
    expect(deps.installer.discardReceipt).toHaveBeenCalledWith("example-theme");
  });

  it("returns false without mutations when the catalog theme is not installed", async () => {
    const deps = dependencies();
    const client = new ThemesClient(deps);
    await client.refresh();

    await expect(client.uninstall("example-theme")).resolves.toBe(false);

    expect(deps.adapter.deleteTheme).not.toHaveBeenCalled();
    expect(deps.installer.discardReceipt).not.toHaveBeenCalled();
  });

  it("returns false without mutations when CSS Loader is not ready", async () => {
    const deps = dependencies();
    deps.adapter.inspect = vi.fn(async () => ({ status: "disabled" as const, themes: [] }));
    const client = new ThemesClient(deps);
    await client.refresh();

    await expect(client.uninstall("example-theme")).resolves.toBe(false);

    expect(deps.adapter.deleteTheme).not.toHaveBeenCalled();
    expect(deps.installer.discardReceipt).not.toHaveBeenCalled();
  });

  it("returns false without mutations while recovery is blocked", async () => {
    const deps = dependencies();
    deps.adapter.inspect = vi.fn(async () => INSTALLED_READY);
    deps.activator.reconcilePendingRecovery = vi.fn(async () => {
      throw new ThemeActivationError("rollback_failed", "still recovering", true);
    });
    const client = new ThemesClient(deps);
    await client.refresh();
    expect(client.getSnapshot().recoveryBlocked).toBe(true);

    await expect(client.uninstall("example-theme")).resolves.toBe(false);

    expect(deps.adapter.deleteTheme).not.toHaveBeenCalled();
    expect(deps.installer.discardReceipt).not.toHaveBeenCalled();
  });

  it("unblocks and tells the user when the previous theme state could not be restored", async () => {
    const deps = dependencies();
    deps.adapter.inspect = vi.fn(async () => INSTALLED_READY);
    let abandoned = false;
    let unblocked = false;
    deps.activator.reconcilePendingRecovery = vi.fn(async () => {
      if (!unblocked) throw new ThemeActivationError("rollback_failed", "still recovering", true);
      return INSTALLED_READY;
    });
    deps.activator.takeAbandonedRecovery = vi.fn(() => {
      const value = abandoned;
      abandoned = false;
      return value;
    });
    const client = new ThemesClient(deps);
    await client.refresh();
    expect(client.getSnapshot()).toMatchObject({ recoveryBlocked: true, recoveryKeptCurrent: false });

    abandoned = true;
    unblocked = true;
    await client.refresh();

    expect(client.getSnapshot()).toMatchObject({ recoveryBlocked: false, recoveryKeptCurrent: true, error: null });
    await expect(client.uninstall("example-theme")).resolves.toBe(true);
    expect(client.getSnapshot().recoveryKeptCurrent).toBe(false);
  });

  it("keeps a confirmed uninstall successful when receipt cleanup fails", async () => {
    const deps = dependencies();
    deps.adapter.inspect = vi.fn(async () => INSTALLED_READY);
    deps.adapter.deleteTheme = vi.fn(async () => READY);
    deps.installer.discardReceipt = vi.fn(async () => { throw new Error("cleanup unavailable"); });
    const client = new ThemesClient(deps);
    await client.refresh();

    await expect(client.uninstall("example-theme")).resolves.toBe(true);
    expect(client.getSnapshot()).toMatchObject({ snapshot: READY, error: null });
  });

  it("publishes a verification failure without discarding the receipt", async () => {
    const deps = dependencies();
    deps.adapter.inspect = vi.fn(async () => INSTALLED_READY);
    deps.adapter.deleteTheme = vi.fn(async () => {
      throw new CssLoaderOperationError(
        "verification_failed",
        "CSS Loader did not confirm the removal of Example Theme",
      );
    });
    const client = new ThemesClient(deps);
    await client.refresh();

    await expect(client.uninstall("example-theme")).resolves.toBe(false);

    expect(deps.installer.discardReceipt).not.toHaveBeenCalled();
    expect(client.getSnapshot()).toMatchObject({
      snapshot: INSTALLED_READY,
      error: "CSS Loader did not confirm the removal of Example Theme",
    });
  });

  it("blocks another mutation while an uninstall is pending", async () => {
    let confirmDeletion!: (snapshot: CssLoaderReadySnapshot) => void;
    const deps = dependencies();
    deps.adapter.inspect = vi.fn(async () => INSTALLED_READY);
    deps.adapter.deleteTheme = vi.fn(() => (
      new Promise<CssLoaderReadySnapshot>((done) => { confirmDeletion = done; })
    ));
    const client = new ThemesClient(deps);
    await client.refresh();

    const uninstalling = client.uninstall("example-theme");
    await vi.waitFor(() => expect(deps.adapter.deleteTheme).toHaveBeenCalledOnce());

    expect(client.getSnapshot().operation).toEqual({
      kind: "uninstalling",
      themeId: "example-theme",
    });
    await expect(client.activate("example-theme")).resolves.toBe(false);
    expect(deps.activator.activate).not.toHaveBeenCalled();

    confirmDeletion(READY);
    await expect(uninstalling).resolves.toBe(true);
  });

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
  it("releases an install rollback that CSS Loader keeps failing to reconcile", async () => {
    const reportFailure = vi.fn();
    const deps = dependencies({ reportFailure });
    deps.installer.pendingRecoveries = vi.fn(async () => [
      { transaction: "stuck", themeName: "Example Theme", previousVersion: "1.0.0" },
    ]);
    deps.adapter.reconcileRecoveredThemes = vi.fn(async () => {
      throw new CssLoaderOperationError("verification_failed", "CSS Loader changed another theme during reload");
    });
    const client = new ThemesClient(deps);

    await client.refresh();
    await client.refresh();
    expect(deps.installer.acknowledgeRollback).not.toHaveBeenCalled();
    expect(client.getSnapshot()).toMatchObject({ errorCode: "verification_failed", recoveryKeptCurrent: false });

    await client.refresh();

    expect(deps.installer.acknowledgeRollback).toHaveBeenCalledWith("stuck");
    expect(reportFailure.mock.calls.map(([failure]) => failure.code)).toEqual([
      "verification_failed",
      "released_after_mismatch",
    ]);
    expect(client.getSnapshot()).toMatchObject({ error: null, errorCode: null, recoveryKeptCurrent: true });
    deps.installer.pendingRecoveries = vi.fn(async () => []);
    await expect(client.install("example-theme", { version: "1.2.3" })).resolves.toBe(true);
  });

  it("never releases an install rollback the backend refuses to recover", async () => {
    const deps = dependencies();
    deps.installer.pendingRecoveries = vi.fn(async () => {
      throw new ThemeInstallError("invalid_journal", "A theme transaction journal requires recovery");
    });
    const client = new ThemesClient(deps);

    for (let attempt = 0; attempt < 4; attempt += 1) await client.refresh();

    expect(deps.installer.acknowledgeRollback).not.toHaveBeenCalled();
    expect(client.getSnapshot()).toMatchObject({
      recoveryBlocked: true,
      recoveryKeptCurrent: false,
      errorCode: "invalid_journal",
    });
  });

  it("reports the failing operation and its code for diagnostics", async () => {
    const reportFailure = vi.fn();
    const deps = dependencies({ reportFailure });
    deps.adapter.reloadTheme = vi.fn(async () => {
      throw new CssLoaderOperationError("verification_failed", "CSS Loader did not register Example Theme v1.2.3");
    });
    const client = new ThemesClient(deps);
    await client.refresh();

    await expect(client.install("example-theme", { version: "1.2.3" })).resolves.toBe(false);

    expect(reportFailure).toHaveBeenCalledWith({
      operation: "installing",
      code: "verification_failed",
      message: "CSS Loader did not register Example Theme v1.2.3",
    });
    expect(client.getSnapshot().errorCode).toBe("verification_failed");
  });

  it("keeps working when failure reporting itself fails", async () => {
    const deps = dependencies({ reportFailure: vi.fn(() => { throw new Error("rpc down"); }) });
    deps.adapter.reloadTheme = vi.fn(async () => { throw new Error("reload failed"); });
    const client = new ThemesClient(deps);
    await client.refresh();

    await expect(client.install("example-theme", { version: "1.2.3" })).resolves.toBe(false);
    expect(client.getSnapshot()).toMatchObject({ error: "reload failed", errorCode: "unknown" });
  });
  describe("section ownership between Hooandee themes", () => {
    const ATLAS: PublishedThemeRelease = {
      ...RELEASE, catalogId: "hooandee-atlas", cssLoaderName: "Atlas", exclusiveGroup: undefined,
    };
    const GALLERY: PublishedThemeRelease = {
      ...RELEASE, catalogId: "hooandee-gallery", cssLoaderName: "Gallery", exclusiveGroup: undefined,
    };
    const section = (name: string, value: string) => ({
      name, defaultValue: "Yes", value, options: ["No", "Yes"], type: "checkbox" as const, rawType: "checkbox",
    });

    function world(atlasEnabled: boolean) {
      const themes = new Map<string, CssLoaderTheme>([
        ["Gallery", { ...INSTALLED_THEME, id: "Gallery", name: "Gallery", displayName: "Gallery", enabled: true,
          patches: [section("Estilizar Inicio", "Yes"), section("Estilizar Ajustes", "Yes")] }],
        ["Atlas", { ...INSTALLED_THEME, id: "Atlas", name: "Atlas", displayName: "Luminous Atlas", enabled: atlasEnabled,
          patches: [section("Estilizar Inicio", "Yes"), section("Estilizar Ajustes", "No")] }],
      ]);
      const snapshot = (): CssLoaderReadySnapshot => ({ status: "ready", themes: [...themes.values()].map((t) => structuredClone(t)) });
      const setEnabled = (name: string, enabled: boolean) => themes.set(name, { ...themes.get(name)!, enabled });
      let stored: Record<string, string> = {};
      const deps = dependencies({
        publication: { check: vi.fn(async () => ({ status: "published" as const, checkedAt: 1, themes: [ATLAS, GALLERY] })) },
        sectionHandoffs: { read: () => stored, write: (next) => { stored = { ...next }; } },
      });
      deps.adapter.inspect = vi.fn(async () => snapshot());
      deps.adapter.requireReady = vi.fn(async () => snapshot());
      deps.adapter.setPatchValue = vi.fn(async (themeName: string, patchName: string, value: string) => {
        const theme = themes.get(themeName)!;
        themes.set(themeName, { ...theme, patches: theme.patches.map((p) => p.name === patchName ? { ...p, value } : p) });
        return snapshot();
      });
      deps.activator.activate = vi.fn(async () => { setEnabled("Atlas", true); return snapshot(); });
      deps.activator.deactivate = vi.fn(async () => { setEnabled("Atlas", false); return snapshot(); });
      const value = (theme: string, patch: string) => themes.get(theme)!.patches.find((p) => p.name === patch)!.value;
      return { deps, value, stored: () => stored };
    }

    it("hands overlapping sections to the theme being activated and gives them back on deactivation", async () => {
      const { deps, value, stored } = world(false);
      const client = new ThemesClient(deps);
      await client.refresh();
      await client.refreshPublication();

      await expect(client.activate("hooandee-atlas")).resolves.toBe(true);

      expect(value("Gallery", "Estilizar Inicio")).toBe("No");
      expect(value("Gallery", "Estilizar Ajustes")).toBe("Yes");
      expect(client.getSnapshot().sectionHandoff).toEqual({ owner: "Luminous Atlas", others: ["Gallery"] });
      expect(stored()).toEqual({ "Gallery\u0000Estilizar Inicio": "Atlas" });

      await expect(client.deactivate("hooandee-atlas")).resolves.toBe(true);

      expect(value("Gallery", "Estilizar Inicio")).toBe("Yes");
      expect(stored()).toEqual({});
    });

    it("gives an activated theme back the sections it had handed to another theme", async () => {
      const { deps, value, stored } = world(true);
      const client = new ThemesClient(deps);
      await client.refresh();
      await client.refreshPublication();
      await client.setPatch("hooandee-gallery", "Estilizar Inicio", "Yes");
      expect(value("Atlas", "Estilizar Inicio")).toBe("No");
      await client.deactivate("hooandee-atlas");

      await expect(client.activate("hooandee-atlas")).resolves.toBe(true);

      expect(value("Atlas", "Estilizar Inicio")).toBe("Yes");
      expect(value("Gallery", "Estilizar Inicio")).toBe("No");
      expect(stored()).toEqual({ "Gallery\u0000Estilizar Inicio": "Atlas" });
    });

    it("lets a section be taken back by turning it on in the other theme", async () => {
      const { deps, value } = world(true);
      const client = new ThemesClient(deps);
      await client.refresh();
      await client.refreshPublication();

      await expect(client.setPatch("hooandee-gallery", "Estilizar Inicio", "Yes")).resolves.toBe(true);

      expect(value("Atlas", "Estilizar Inicio")).toBe("No");
      expect(value("Gallery", "Estilizar Inicio")).toBe("Yes");
    });

    it("keeps a confirmed activation when a section handoff cannot be written", async () => {
      const { deps } = world(false);
      const reportFailure = vi.fn();
      deps.reportFailure = reportFailure;
      const setPatchValue = deps.adapter.setPatchValue;
      deps.adapter.setPatchValue = vi.fn(async () => { throw new CssLoaderOperationError("mutation_failed", "nope"); });
      const client = new ThemesClient(deps);
      await client.refresh();
      await client.refreshPublication();

      await expect(client.activate("hooandee-atlas")).resolves.toBe(true);

      expect(client.getSnapshot()).toMatchObject({ error: null, sectionHandoff: null });
      expect(reportFailure).toHaveBeenCalledWith(expect.objectContaining({ code: "section_handoff_failed" }));
      expect(setPatchValue).not.toHaveBeenCalled();
    });
  });
});

describe("ThemesClient cleanup", () => {
  const OTHER: CssLoaderTheme = { ...INSTALLED_THEME, id: "Other", name: "Other", displayName: "Other" };

  it("records what it turns off before touching CSS Loader, keeping catalog themes", async () => {
    const order: string[] = [];
    const before: CssLoaderReadySnapshot = { status: "ready", themes: [INSTALLED_THEME, OTHER] };
    const after: CssLoaderReadySnapshot = { status: "ready", themes: [INSTALLED_THEME, { ...OTHER, enabled: false }] };
    const disableAllExcept = vi.fn(async () => { order.push("css-loader"); return after; });
    const setAside = vi.fn(async () => { order.push("set-aside"); });
    const deps = dependencies({ cleanup: { setAside, restore: vi.fn(async () => []), acknowledgeRestore: vi.fn(async () => {}) } });
    deps.adapter.requireReady = vi.fn(async () => before);
    deps.adapter.inspect = vi.fn(async () => before);
    deps.adapter.disableAllExcept = disableAllExcept;
    const client = new ThemesClient(deps);
    await client.refresh();

    await expect(client.cleanUp(["Local Hooandee"])).resolves.toBe(true);

    expect(order).toEqual(["set-aside", "css-loader"]);
    expect(setAside).toHaveBeenCalledWith(["Other"]);
    expect(disableAllExcept).toHaveBeenCalledWith(before, new Set(["Local Hooandee", "Example Theme"]));
    expect(client.getSnapshot()).toMatchObject({ snapshot: after, operation: null, error: null });
  });

  it("does not touch CSS Loader when the backend refuses to record the cleanup", async () => {
    const disableAllExcept = vi.fn(async () => READY);
    const failure = Object.assign(new Error("refused"), { code: "invalid_record" });
    const deps = dependencies({ cleanup: { setAside: vi.fn(async () => { throw failure; }), restore: vi.fn(async () => []), acknowledgeRestore: vi.fn(async () => {}) } });
    deps.adapter.disableAllExcept = disableAllExcept;
    const client = new ThemesClient(deps);

    await expect(client.cleanUp([])).resolves.toBe(false);

    expect(disableAllExcept).not.toHaveBeenCalled();
    expect(client.getSnapshot().errorCode).toBe("invalid_record");
  });

  it("brings back the recorded themes on undo and only then forgets them", async () => {
    const enableAgain = vi.fn(async () => READY);
    const acknowledgeRestore = vi.fn(async () => {});
    const deps = dependencies({ cleanup: { setAside: vi.fn(async () => {}), restore: vi.fn(async () => ["Other"]), acknowledgeRestore } });
    deps.adapter.enableAgain = enableAgain;
    const client = new ThemesClient(deps);

    await expect(client.undoCleanup([])).resolves.toBe(true);

    expect(enableAgain).toHaveBeenCalledWith(READY, new Set(), ["Other"]);
    expect(acknowledgeRestore).toHaveBeenCalledTimes(1);
  });

  it("keeps the themes to enable again when CSS Loader cannot confirm them", async () => {
    const acknowledgeRestore = vi.fn(async () => {});
    const deps = dependencies({ cleanup: { setAside: vi.fn(async () => {}), restore: vi.fn(async () => ["Other"]), acknowledgeRestore } });
    deps.adapter.enableAgain = vi.fn(async () => {
      throw new CssLoaderOperationError("verification_failed", "CSS Loader did not enable a restored theme");
    });
    const client = new ThemesClient(deps);

    await expect(client.undoCleanup([])).resolves.toBe(false);

    expect(acknowledgeRestore).not.toHaveBeenCalled();
  });

  it("brings folders back without CSS Loader and leaves the themes for later", async () => {
    const restore = vi.fn(async () => ["Other"]);
    const acknowledgeRestore = vi.fn(async () => {});
    const enableAgain = vi.fn(async () => READY);
    const deps = dependencies({ cleanup: { setAside: vi.fn(async () => {}), restore, acknowledgeRestore } });
    deps.adapter.inspect = vi.fn(async () => ({ status: "missing" as const, themes: [] }));
    deps.adapter.enableAgain = enableAgain;
    const client = new ThemesClient(deps);

    await expect(client.undoCleanup([])).resolves.toBe(true);

    expect(restore).toHaveBeenCalledTimes(1);
    expect(enableAgain).not.toHaveBeenCalled();
    expect(acknowledgeRestore).not.toHaveBeenCalled();
  });

  it("removes leftover styles once no theme is left enabled", async () => {
    const removeLeftoverStyles = vi.fn();
    const before: CssLoaderReadySnapshot = { status: "ready", themes: [OTHER] };
    const deps = dependencies({ cleanup: { setAside: vi.fn(async () => {}), restore: vi.fn(async () => []), acknowledgeRestore: vi.fn(async () => {}) } });
    deps.adapter.requireReady = vi.fn(async () => before);
    deps.adapter.disableAllExcept = vi.fn(async () => ({ status: "ready" as const, themes: [{ ...OTHER, enabled: false }] }));
    const client = new ThemesClient(deps);

    await expect(client.cleanUp([], removeLeftoverStyles)).resolves.toBe(true);

    expect(removeLeftoverStyles).toHaveBeenCalledTimes(1);
  });

  it("fails closed without a cleanup backend", async () => {
    const client = new ThemesClient(dependencies());

    await expect(client.cleanUp([])).resolves.toBe(false);
    expect(client.getSnapshot().errorCode).toBe("transport");
  });
});

describe("ThemesClient cleanup privacy", () => {
  it("reports cleanup failures without CSS Loader's theme names", async () => {
    const reportFailure = vi.fn();
    const deps = dependencies({ reportFailure, cleanup: { setAside: vi.fn(async () => {}), restore: vi.fn(async () => []), acknowledgeRestore: vi.fn(async () => {}) } });
    deps.adapter.disableAllExcept = vi.fn(async () => {
      throw new CssLoaderOperationError("mutation_failed", "Did not find theme Someone Private.profile");
    });
    const client = new ThemesClient(deps);

    await expect(client.cleanUp([])).resolves.toBe(false);

    expect(reportFailure).toHaveBeenCalledWith({
      operation: "cleaning",
      code: "mutation_failed",
      message: "CSS Loader could not finish the theme cleanup",
    });
  });
});

describe("ThemesClient cleanup without CSS Loader", () => {
  it("sets folders aside and removes leftover styles without calling CSS Loader", async () => {
    const setAside = vi.fn(async () => {});
    const removeLeftoverStyles = vi.fn();
    const disableAllExcept = vi.fn(async () => READY);
    const deps = dependencies({ cleanup: { setAside, restore: vi.fn(async () => []), acknowledgeRestore: vi.fn(async () => {}) } });
    deps.adapter.inspect = vi.fn(async () => ({ status: "disabled" as const, themes: [] }));
    deps.adapter.disableAllExcept = disableAllExcept;
    const client = new ThemesClient(deps);

    await expect(client.cleanUp([], removeLeftoverStyles)).resolves.toBe(true);

    expect(setAside).toHaveBeenCalledWith([]);
    expect(removeLeftoverStyles).toHaveBeenCalledTimes(1);
    expect(disableAllExcept).not.toHaveBeenCalled();
  });
});

describe("ThemesClient cleanup with several Hooandee themes", () => {
  it("turns the other Hooandee themes off through the activator before reloading CSS Loader", async () => {
    const second: PublishedThemeRelease = { ...RELEASE, catalogId: "second-theme", cssLoaderName: "Second Theme" };
    const order: string[] = [];
    const both: CssLoaderReadySnapshot = {
      status: "ready",
      themes: [INSTALLED_THEME, { ...INSTALLED_THEME, id: "Second Theme", name: "Second Theme", displayName: "Second Theme" }],
    };
    const deps = dependencies({
      publication: { check: vi.fn(async () => ({ status: "published" as const, checkedAt: 10, themes: [RELEASE, second] })) },
      cleanup: { setAside: vi.fn(async () => { order.push("set-aside"); }), restore: vi.fn(async () => []), acknowledgeRestore: vi.fn(async () => {}) },
    });
    deps.adapter.inspect = vi.fn(async () => both);
    deps.adapter.requireReady = vi.fn(async () => both);
    deps.activator.deactivate = vi.fn(async (themeId: string) => { order.push(`deactivate:${themeId}`); return READY; });
    deps.adapter.disableAllExcept = vi.fn(async () => { order.push("css-loader"); return READY; });
    const client = new ThemesClient(deps);
    await client.refresh();
    await client.refreshPublication();

    await expect(client.cleanUp([], undefined, "Example Theme")).resolves.toBe(true);

    expect(order).toEqual(["deactivate:second-theme", "set-aside", "css-loader"]);
  });
});
