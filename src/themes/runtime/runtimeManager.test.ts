import { describe, expect, it, vi } from "vitest";

import type { CssLoaderSnapshot } from "../cssLoaderTypes";
import { ThemeRuntimeManager, type ThemeRuntimeModule } from "./runtimeManager";

function snapshot(activeTheme?: string, patchValue?: string): CssLoaderSnapshot {
  return {
    status: "ready",
    backendVersion: 9,
    themes: activeTheme ? [{
      id: activeTheme,
      name: activeTheme,
      displayName: activeTheme,
      version: "0.1.0",
      author: "Hooandee",
      enabled: true,
      patches: patchValue === undefined ? [] : [{
        name: "Animaciones de parrilla",
        defaultValue: "Yes",
        value: patchValue,
        options: ["No", "Yes"],
        type: "checkbox",
        rawType: "checkbox",
      }],
    }] : [],
  };
}

describe("ThemeRuntimeManager", () => {
  it("mounts only the known runtime matching the active catalog theme", () => {
    const stop = vi.fn();
    const module: ThemeRuntimeModule = { id: "obsidian-bloom", mount: vi.fn(() => stop) };
    const manager = new ThemeRuntimeManager({ modules: [module] });

    manager.reconcile(snapshot("Third Party Theme"));
    expect(module.mount).not.toHaveBeenCalled();

    manager.reconcile(snapshot("Hooandee Obsidian Bloom"));
    manager.reconcile(snapshot("Hooandee Obsidian Bloom"));
    expect(module.mount).toHaveBeenCalledOnce();

    manager.reconcile(snapshot());
    expect(stop).toHaveBeenCalledOnce();
  });

  it("fails closed and restores the current runtime when CSS Loader is unavailable", () => {
    const stop = vi.fn();
    const manager = new ThemeRuntimeManager({
      modules: [{ id: "obsidian-bloom", mount: () => stop }],
    });
    manager.reconcile(snapshot("Hooandee Obsidian Bloom"));

    manager.reconcile({ status: "error", themes: [], error: { code: "transport", message: "offline" } });
    manager.dispose();

    expect(stop).toHaveBeenCalledOnce();
  });

  it("restores even when a module throws while mounting", () => {
    const manager = new ThemeRuntimeManager({
      modules: [{ id: "obsidian-bloom", mount: () => { throw new Error("broken"); } }],
    });

    expect(() => manager.reconcile(snapshot("Hooandee Obsidian Bloom"))).not.toThrow();
    expect(manager.activeModuleId()).toBeNull();
  });

  it("reconciles a known runtime when verified CSS Loader patch values change", () => {
    const stops = [vi.fn(), vi.fn()];
    const module: ThemeRuntimeModule = {
      id: "obsidian-bloom",
      mount: vi.fn(() => stops.shift() ?? vi.fn()),
    };
    const manager = new ThemeRuntimeManager({ modules: [module] });

    manager.reconcile(snapshot("Hooandee Obsidian Bloom", "Yes"));
    manager.reconcile(snapshot("Hooandee Obsidian Bloom", "Yes"));
    manager.reconcile(snapshot("Hooandee Obsidian Bloom", "No"));

    expect(module.mount).toHaveBeenCalledTimes(2);
    expect(module.mount).toHaveBeenLastCalledWith(expect.objectContaining({
      patches: [expect.objectContaining({ name: "Animaciones de parrilla", value: "No" })],
    }));
  });

  it("does not remount when CSS Loader returns the same patches in another order", () => {
    const module: ThemeRuntimeModule = {
      id: "obsidian-bloom",
      mount: vi.fn(() => vi.fn()),
    };
    const manager = new ThemeRuntimeManager({ modules: [module] });
    const theme = snapshot("Hooandee Obsidian Bloom", "Yes");
    if (theme.status !== "ready" || !theme.themes[0]) throw new Error("Invalid test fixture");
    const secondPatch = {
      ...theme.themes[0].patches[0],
      name: "Modo claro",
      value: "No",
    };
    const reordered = {
      ...theme,
      themes: [{
        ...theme.themes[0],
        patches: [secondPatch, ...theme.themes[0].patches],
      }],
    };

    manager.reconcile({
      ...theme,
      themes: [{
        ...theme.themes[0],
        patches: [...theme.themes[0].patches, secondPatch],
      }],
    });
    manager.reconcile(reordered);

    expect(module.mount).toHaveBeenCalledOnce();
  });
});
