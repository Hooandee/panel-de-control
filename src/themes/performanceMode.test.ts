import { describe, expect, it, vi } from "vitest";

import type { CssLoaderReadySnapshot } from "./cssLoaderAdapter";
import type { CssLoaderPatch, CssLoaderTheme } from "./cssLoaderTypes";
import { PERFORMANCE_PATCH, planPerformanceMode, supportsPerformanceMode } from "./performanceMode";
import type { PublishedThemeRelease } from "./remotePublication";
import { ThemesClient, type ThemesDependencies } from "./themesClient";

const RELEASE: PublishedThemeRelease = {
  catalogId: "hooandee-eclipse",
  cssLoaderName: "Hooandee Eclipse",
  publishedVersion: "0.2.6",
  displayName: { es: "Eclipse", en: "Eclipse", it: "Eclipse" },
  description: { es: "", en: "", it: "" },
  author: "Hooandee",
  tags: [],
  notes: {},
  compatibility: "compatible",
};

function performancePatch(value: string): CssLoaderPatch {
  return { name: PERFORMANCE_PATCH, defaultValue: "No", value, options: ["No", "Yes"], type: "checkbox", rawType: "checkbox" };
}

function theme(name: string, patches: CssLoaderPatch[], enabled = true): CssLoaderTheme {
  return { id: name, name, displayName: name, version: "0.2.6", author: "Hooandee", enabled, patches };
}

function ready(...themes: CssLoaderTheme[]): CssLoaderReadySnapshot {
  return { status: "ready", themes };
}

function client(initial: CssLoaderReadySnapshot, stored: boolean | null = false) {
  let current = initial;
  let mode = stored;
  const setPatchValue = vi.fn(async (themeName: string, patchName: string, value: string) => {
    current = ready(...current.themes.map((entry) => entry.name !== themeName ? entry : {
      ...entry,
      patches: entry.patches.map((patch) => patch.name === patchName ? { ...patch, value } : patch),
    }));
    return current;
  });
  const reportFailure = vi.fn();
  const deps: ThemesDependencies = {
    adapter: {
      inspect: vi.fn(async () => current),
      requireReady: vi.fn(async () => current),
      reloadTheme: vi.fn(async () => current),
      restoreThemeSnapshot: vi.fn(async () => current),
      reconcileRecoveredThemes: vi.fn(async () => current),
      setPatchValue,
      deleteTheme: vi.fn(async () => current),
    },
    installer: {
      prepare: vi.fn(),
      commit: vi.fn(async () => undefined),
      discardReceipt: vi.fn(async () => undefined),
      rollback: vi.fn(async () => undefined),
      pendingRecoveries: vi.fn(async () => []),
      acknowledgeRollback: vi.fn(async () => undefined),
    },
    activator: {
      activate: vi.fn(async () => current),
      deactivate: vi.fn(async () => current),
    },
    publication: { check: vi.fn(async () => ({ status: "published" as const, checkedAt: 1, themes: [RELEASE] })) },
    performanceMode: { read: () => mode, write: (on) => { mode = on; } },
    reportFailure,
  };
  const themes = new ThemesClient(deps);
  return {
    themes,
    deps,
    reset: (snapshot: CssLoaderReadySnapshot) => { current = snapshot; },
    setPatchValue,
    reportFailure,
    stored: () => mode,
    setStored: (on: boolean | null) => { mode = on; },
    current: () => current,
  };
}

async function settle(themes: ThemesClient): Promise<void> {
  await vi.waitFor(() => expect(themes.getSnapshot().operation).toBeNull());
}

describe("performance mode plan", () => {
  it("only targets Hooandee themes that ship the reserved checkbox and are out of step", () => {
    const hooandee = new Set(["Hooandee Eclipse", "Hooandee Gallery"]);
    const plan = planPerformanceMode([
      theme("Hooandee Eclipse", [performancePatch("No")]),
      theme("Hooandee Gallery", []),
      theme("Third Party", [performancePatch("No")]),
    ], hooandee, true);
    expect(plan).toEqual([{ themeName: "Hooandee Eclipse", patchName: PERFORMANCE_PATCH, value: "Yes" }]);
  });

  it("ignores a same-named option that is not the on/off checkbox", () => {
    const dropdown = { ...performancePatch("No"), type: "dropdown" as const };
    expect(supportsPerformanceMode(theme("Hooandee Eclipse", [dropdown]))).toBe(false);
  });
});

describe("ThemesClient performance mode", () => {
  it("stores the choice and switches every supporting Hooandee theme", async () => {
    const setup = client(ready(theme("Hooandee Eclipse", [performancePatch("No")], false)));
    await setup.themes.refresh();
    await setup.themes.refreshPublication();

    await expect(setup.themes.setPerformanceMode(true)).resolves.toBe(true);

    expect(setup.stored()).toBe(true);
    expect(setup.themes.getSnapshot().performanceMode).toBe(true);
    expect(setup.setPatchValue).toHaveBeenCalledWith("Hooandee Eclipse", PERFORMANCE_PATCH, "Yes");
  });

  it("applies the mode to a theme as it is activated", async () => {
    const setup = client(ready(theme("Hooandee Eclipse", [performancePatch("Yes")], false)), true);
    await setup.themes.refreshPublication();
    await setup.themes.refresh();
    await settle(setup.themes);
    setup.deps.activator.activate = vi.fn(async () => {
      setup.reset(ready(theme("Hooandee Eclipse", [performancePatch("No")])));
      return setup.current();
    });

    await expect(setup.themes.activate("hooandee-eclipse")).resolves.toBe(true);
    await settle(setup.themes);

    expect(setup.setPatchValue).toHaveBeenCalledWith("Hooandee Eclipse", PERFORMANCE_PATCH, "Yes");
  });

  it("brings a theme back in step on refresh, but does not retry one that refused", async () => {
    const setup = client(ready(theme("Hooandee Eclipse", [performancePatch("Yes")])));
    await setup.themes.refreshPublication();
    await setup.themes.refresh();
    await settle(setup.themes);
    expect(setup.setPatchValue).toHaveBeenCalledWith("Hooandee Eclipse", PERFORMANCE_PATCH, "No");

    setup.setStored(true);
    setup.setPatchValue.mockRejectedValue(Object.assign(new Error("refused"), { code: "mutation_failed" }));
    await setup.themes.refresh();
    await settle(setup.themes);
    await setup.themes.refresh();
    await settle(setup.themes);

    expect(setup.setPatchValue.mock.calls.filter(([, , value]) => value === "Yes")).toHaveLength(1);
    expect(setup.reportFailure).toHaveBeenCalledWith(expect.objectContaining({
      operation: "performance",
      code: "performance_mode_failed",
    }));
  });

  it("keeps an activation that succeeded even if the theme refuses the mode", async () => {
    const setup = client(ready(theme("Hooandee Eclipse", [performancePatch("No")], false)), true);
    setup.setPatchValue.mockRejectedValue(new Error("refused"));
    await setup.themes.refreshPublication();
    await setup.themes.refresh();
    await settle(setup.themes);

    await expect(setup.themes.activate("hooandee-eclipse")).resolves.toBe(true);

    expect(setup.themes.getSnapshot().error).toBeNull();
  });

  it("picks up the stored choice once preferences arrive from the backend", async () => {
    const setup = client(ready(theme("Hooandee Eclipse", [performancePatch("Yes")])));
    await setup.themes.refreshPublication();
    setup.setStored(true);

    await setup.themes.refresh();
    await settle(setup.themes);

    expect(setup.themes.getSnapshot().performanceMode).toBe(true);
    expect(setup.setPatchValue).not.toHaveBeenCalled();
  });

  it("adopts the option a user ticked in an older Panel instead of undoing it", async () => {
    const setup = client(ready(theme("Hooandee Eclipse", [performancePatch("Yes")])), null);
    await setup.themes.refreshPublication();

    await setup.themes.refresh();
    await settle(setup.themes);

    expect(setup.stored()).toBe(true);
    expect(setup.themes.getSnapshot().performanceMode).toBe(true);
    expect(setup.setPatchValue).not.toHaveBeenCalled();
  });

  it("leaves everything alone while no choice exists and nothing was ticked", async () => {
    const setup = client(ready(theme("Hooandee Eclipse", [performancePatch("No")])), null);
    await setup.themes.refreshPublication();

    await setup.themes.refresh();
    await settle(setup.themes);

    expect(setup.stored()).toBeNull();
    expect(setup.setPatchValue).not.toHaveBeenCalled();
  });

  it("follows a change made in CSS Loader's own menu instead of undoing it", async () => {
    const setup = client(ready(theme("Hooandee Eclipse", [performancePatch("No")])), false);
    await setup.themes.refreshPublication();
    await setup.themes.refresh();
    await settle(setup.themes);

    setup.reset(ready(theme("Hooandee Eclipse", [performancePatch("Yes")]), theme("Hooandee Gallery", [performancePatch("No")])));
    await setup.themes.refresh();
    await settle(setup.themes);

    expect(setup.stored()).toBe(true);
    expect(setup.themes.getSnapshot().performanceMode).toBe(true);
    expect(setup.setPatchValue).not.toHaveBeenCalledWith("Hooandee Eclipse", PERFORMANCE_PATCH, "No");
  });

  it("keeps the notice of the last operation while it reconciles in the background", async () => {
    const setup = client(ready(theme("Hooandee Eclipse", [performancePatch("No")])), true);
    await setup.themes.refresh();
    await setup.themes.refreshPublication();
    await vi.waitFor(() => expect(setup.setPatchValue).toHaveBeenCalledWith("Hooandee Eclipse", PERFORMANCE_PATCH, "Yes"));

    expect(setup.themes.getSnapshot().operation).toBeNull();
  });
});
