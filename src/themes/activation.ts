import type { CssLoaderSnapshot } from "./cssLoaderTypes";
import type { PublishedThemeRelease } from "./remotePublication";

export interface ThemeActivationAdapter {
  inspect(): Promise<CssLoaderSnapshot>;
  setThemeState(name: string, enabled: boolean): Promise<CssLoaderSnapshot>;
}

export type ThemeActivationErrorCode =
  | "busy"
  | "not_ready"
  | "unknown_theme"
  | "not_installed"
  | "activation_failed"
  | "deactivation_failed"
  | "rollback_failed";

export class ThemeActivationError extends Error {
  constructor(
    readonly code: ThemeActivationErrorCode,
    message: string,
    readonly restorationFailed = false,
  ) {
    super(message);
    this.name = "ThemeActivationError";
  }
}

function requireReady(snapshot: CssLoaderSnapshot): asserts snapshot is CssLoaderSnapshot & { status: "ready" } {
  if (snapshot.status !== "ready") {
    throw new ThemeActivationError("not_ready", `CSS Loader is ${snapshot.status}`);
  }
}

function catalogByCssLoaderName(catalog: readonly PublishedThemeRelease[]): Map<string, PublishedThemeRelease> {
  return new Map(catalog.map((theme) => [theme.cssLoaderName, theme]));
}

function statesOf(
  snapshot: CssLoaderSnapshot,
  catalogNames: ReadonlySet<string>,
): Map<string, boolean> {
  return new Map(snapshot.themes
    .filter((theme) => catalogNames.has(theme.name))
    .map((theme) => [theme.name, theme.enabled]));
}

function thirdPartyStates(
  snapshot: CssLoaderSnapshot,
  catalogNames: ReadonlySet<string>,
): Map<string, boolean> {
  return new Map(snapshot.themes
    .filter((theme) => !catalogNames.has(theme.name))
    .map((theme) => [theme.name, theme.enabled]));
}

function sameStates(expected: ReadonlyMap<string, boolean>, snapshot: CssLoaderSnapshot): boolean {
  const actual = new Map(snapshot.themes.map((theme) => [theme.name, theme.enabled]));
  return [...expected].every(([name, enabled]) => actual.get(name) === enabled);
}

export class ThemeActivator {
  private running = false;

  constructor(
    private readonly adapter: ThemeActivationAdapter,
  ) {}

  activate(themeId: string, catalog: readonly PublishedThemeRelease[]): Promise<CssLoaderSnapshot> {
    if (this.running) {
      return Promise.reject(new ThemeActivationError("busy", "A theme activation is already running"));
    }
    this.running = true;
    return this.runActivation(themeId, catalog).finally(() => {
      this.running = false;
    });
  }

  deactivate(themeId: string, catalog: readonly PublishedThemeRelease[]): Promise<CssLoaderSnapshot> {
    if (this.running) {
      return Promise.reject(new ThemeActivationError("busy", "A theme operation is already running"));
    }
    this.running = true;
    return this.runDeactivation(themeId, catalog).finally(() => {
      this.running = false;
    });
  }

  private async runActivation(
    themeId: string,
    catalog: readonly PublishedThemeRelease[],
  ): Promise<CssLoaderSnapshot> {
    const target = catalog.find((theme) => theme.catalogId === themeId);
    if (!target) throw new ThemeActivationError("unknown_theme", `Unknown published theme: ${themeId}`);

    const initial = await this.adapter.inspect();
    requireReady(initial);
    if (!initial.themes.some((theme) => theme.name === target.cssLoaderName)) {
      throw new ThemeActivationError("not_installed", `${target.cssLoaderName} is not installed`);
    }

    const catalogEntries = catalogByCssLoaderName(catalog);
    const catalogNames = new Set(catalogEntries.keys());
    const initialManaged = statesOf(initial, catalogNames);
    const initialThirdParty = thirdPartyStates(initial, catalogNames);
    const conflicts = initial.themes.filter((theme) => {
      const entry = catalogEntries.get(theme.name);
      return theme.enabled
        && theme.name !== target.cssLoaderName
        && entry?.exclusiveGroup !== undefined
      && entry.exclusiveGroup === target.exclusiveGroup;
    });
    const expectedManaged = new Map(initialManaged);
    conflicts.forEach((conflict) => expectedManaged.set(conflict.name, false));
    expectedManaged.set(target.cssLoaderName, true);

    try {
      for (const conflict of conflicts) {
        await this.adapter.setThemeState(conflict.name, false);
      }
      if (!initialManaged.get(target.cssLoaderName)) {
        await this.adapter.setThemeState(target.cssLoaderName, true);
      }

      const finalSnapshot = await this.adapter.inspect();
      requireReady(finalSnapshot);
      if (!sameStates(expectedManaged, finalSnapshot)) {
        throw new Error("CSS Loader did not confirm the requested managed theme state");
      }
      if (!sameStates(initialThirdParty, finalSnapshot)) {
        throw new Error("A third-party theme changed during managed theme activation");
      }
      return finalSnapshot;
    } catch (activationError) {
      try {
        await this.restoreCatalogStates(initialManaged, catalogNames);
      } catch {
        throw new ThemeActivationError(
          "rollback_failed",
          "Activation failed and the previous managed theme state could not be restored",
          true,
        );
      }
      const detail = activationError instanceof Error ? activationError.message : "unknown failure";
      throw new ThemeActivationError("activation_failed", `Theme activation failed: ${detail}`);
    }
  }

  private async runDeactivation(
    themeId: string,
    catalog: readonly PublishedThemeRelease[],
  ): Promise<CssLoaderSnapshot> {
    const target = catalog.find((theme) => theme.catalogId === themeId);
    if (!target) throw new ThemeActivationError("unknown_theme", `Unknown published theme: ${themeId}`);

    const initial = await this.adapter.inspect();
    requireReady(initial);
    const installed = initial.themes.find((theme) => theme.name === target.cssLoaderName);
    if (!installed) throw new ThemeActivationError("not_installed", `${target.cssLoaderName} is not installed`);
    if (!installed.enabled) return initial;

    const catalogNames = new Set(catalog.map((theme) => theme.cssLoaderName));
    const initialManaged = statesOf(initial, catalogNames);
    const initialThirdParty = thirdPartyStates(initial, catalogNames);
    const expectedManaged = new Map(initialManaged);
    expectedManaged.set(target.cssLoaderName, false);
    try {
      await this.adapter.setThemeState(target.cssLoaderName, false);
      const finalSnapshot = await this.adapter.inspect();
      requireReady(finalSnapshot);
      if (!sameStates(expectedManaged, finalSnapshot)) {
        throw new Error("CSS Loader did not confirm the requested managed theme state");
      }
      if (!sameStates(initialThirdParty, finalSnapshot)) {
        throw new Error("A third-party theme changed during managed theme deactivation");
      }
      return finalSnapshot;
    } catch (deactivationError) {
      try {
        await this.restoreCatalogStates(initialManaged, catalogNames);
      } catch {
        throw new ThemeActivationError(
          "rollback_failed",
          "Deactivation failed and the previous managed theme state could not be restored",
          true,
        );
      }
      const detail = deactivationError instanceof Error ? deactivationError.message : "unknown failure";
      throw new ThemeActivationError("deactivation_failed", `Theme deactivation failed: ${detail}`);
    }
  }

  private async restoreCatalogStates(
    expected: ReadonlyMap<string, boolean>,
    catalogNames: ReadonlySet<string>,
  ): Promise<void> {
    let currentStates: Map<string, boolean> | null = null;
    try {
      const current = await this.adapter.inspect();
      requireReady(current);
      currentStates = statesOf(current, catalogNames);
    } catch {}
    const restoration = [...expected]
      .filter(([name, enabled]) => currentStates?.get(name) !== enabled)
      .reverse();
    for (const [name, enabled] of restoration) {
      await this.adapter.setThemeState(name, enabled);
    }
    const restored = await this.adapter.inspect();
    requireReady(restored);
    if (!sameStates(expected, restored)) {
      throw new Error("Managed theme state does not match the operation snapshot");
    }
  }
}
