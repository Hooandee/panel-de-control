import type { CssLoaderSnapshot } from "./cssLoaderTypes";
import type { ThemeCatalog, ThemeCatalogEntry } from "./types";

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

function catalogByCssLoaderName(catalog: ThemeCatalog): Map<string, ThemeCatalogEntry> {
  return new Map(catalog.themes.map((theme) => [theme.cssLoaderName, theme]));
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
    private readonly catalog: ThemeCatalog,
  ) {}

  activate(themeId: string): Promise<CssLoaderSnapshot> {
    if (this.running) {
      return Promise.reject(new ThemeActivationError("busy", "A theme activation is already running"));
    }
    this.running = true;
    return this.runActivation(themeId).finally(() => {
      this.running = false;
    });
  }

  private async runActivation(themeId: string): Promise<CssLoaderSnapshot> {
    const target = this.catalog.themes.find((theme) => theme.id === themeId);
    if (!target) throw new ThemeActivationError("unknown_theme", `Unknown Hooandee theme: ${themeId}`);

    const initial = await this.adapter.inspect();
    requireReady(initial);
    if (!initial.themes.some((theme) => theme.name === target.cssLoaderName)) {
      throw new ThemeActivationError("not_installed", `${target.name} is not installed`);
    }

    const catalogEntries = catalogByCssLoaderName(this.catalog);
    const catalogNames = new Set(catalogEntries.keys());
    const initialHooandee = statesOf(initial, catalogNames);
    const initialThirdParty = thirdPartyStates(initial, catalogNames);
    const conflicts = initial.themes.filter((theme) => {
      const entry = catalogEntries.get(theme.name);
      return theme.enabled
        && theme.name !== target.cssLoaderName
        && entry?.exclusiveGroup !== undefined
        && entry.exclusiveGroup === target.exclusiveGroup;
    });

    try {
      for (const conflict of conflicts) {
        await this.adapter.setThemeState(conflict.name, false);
      }
      if (!initialHooandee.get(target.cssLoaderName)) {
        await this.adapter.setThemeState(target.cssLoaderName, true);
      }

      const finalSnapshot = await this.adapter.inspect();
      requireReady(finalSnapshot);
      const finalTarget = finalSnapshot.themes.find((theme) => theme.name === target.cssLoaderName);
      const conflictsRemain = conflicts.some((conflict) =>
        finalSnapshot.themes.find((theme) => theme.name === conflict.name)?.enabled !== false);
      if (!finalTarget?.enabled || conflictsRemain) {
        throw new Error("CSS Loader did not confirm the requested Hooandee state");
      }
      if (!sameStates(initialThirdParty, finalSnapshot)) {
        throw new Error("A third-party theme changed during Hooandee activation");
      }
      return finalSnapshot;
    } catch (activationError) {
      try {
        let currentStates: Map<string, boolean> | null = null;
        try {
          const current = await this.adapter.inspect();
          requireReady(current);
          currentStates = statesOf(current, catalogNames);
        } catch {}
        const restoration = [...initialHooandee]
          .filter(([name, enabled]) => currentStates?.get(name) !== enabled)
          .reverse();
        for (const [name, enabled] of restoration) {
          await this.adapter.setThemeState(name, enabled);
        }
        const restored = await this.adapter.inspect();
        requireReady(restored);
        if (!sameStates(initialHooandee, restored)) {
          throw new Error("Hooandee state does not match the activation snapshot");
        }
      } catch {
        throw new ThemeActivationError(
          "rollback_failed",
          "Activation failed and the previous Hooandee state could not be restored",
          true,
        );
      }
      const detail = activationError instanceof Error ? activationError.message : "unknown failure";
      throw new ThemeActivationError("activation_failed", `Theme activation failed: ${detail}`);
    }
  }
}
