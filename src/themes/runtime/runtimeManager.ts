import { LOCAL_THEME_CATALOG } from "../catalog";
import type { CssLoaderSnapshot, CssLoaderTheme } from "../cssLoaderTypes";
import type { ThemeCatalog } from "../types";

export interface ThemeRuntimeModule {
  id: string;
  mount(theme: CssLoaderTheme): () => void;
}

interface RuntimeSelection {
  moduleId: string;
  theme: CssLoaderTheme;
  fingerprint: string;
}

interface RuntimeManagerOptions {
  modules: readonly ThemeRuntimeModule[];
  catalog?: ThemeCatalog;
}

export class ThemeRuntimeManager {
  private readonly modules: ReadonlyMap<string, ThemeRuntimeModule>;
  private readonly catalog: ThemeCatalog;
  private activeId: string | null = null;
  private activeFingerprint: string | null = null;
  private stopActive: (() => void) | null = null;

  constructor({ modules, catalog = LOCAL_THEME_CATALOG }: RuntimeManagerOptions) {
    this.modules = new Map(modules.map((module) => [module.id, module]));
    this.catalog = catalog;
  }

  activeModuleId(): string | null {
    return this.activeId;
  }

  reconcile(snapshot: CssLoaderSnapshot): void {
    const selection = snapshot.status === "ready" ? this.runtimeFor(snapshot) : null;
    if (
      selection?.moduleId === this.activeId
      && selection.fingerprint === this.activeFingerprint
    ) return;
    this.stop();
    if (!selection) return;
    const module = this.modules.get(selection.moduleId);
    if (!module) return;
    try {
      const stop = module.mount(selection.theme);
      this.activeId = selection.moduleId;
      this.activeFingerprint = selection.fingerprint;
      this.stopActive = stop;
    } catch {
      this.activeId = null;
      this.activeFingerprint = null;
      this.stopActive = null;
    }
  }

  dispose(): void {
    this.stop();
  }

  private runtimeFor(snapshot: CssLoaderSnapshot): RuntimeSelection | null {
    const activeThemes = new Map(snapshot.themes
      .filter((theme) => theme.enabled)
      .map((theme) => [theme.name, theme]));
    const activeRuntimeEntries = this.catalog.themes.flatMap((entry) => {
      const theme = activeThemes.get(entry.cssLoaderName);
      return entry.runtime && theme ? [{ entry, theme }] : [];
    });
    if (activeRuntimeEntries.length !== 1) return null;
    const [{ entry, theme }] = activeRuntimeEntries;
    return {
      moduleId: entry.runtime!.moduleId,
      theme,
      fingerprint: JSON.stringify({
        version: theme.version,
        patches: theme.patches.map((patch) => [patch.name, patch.value]),
      }),
    };
  }

  private stop(): void {
    try {
      this.stopActive?.();
    } catch {}
    this.stopActive = null;
    this.activeId = null;
    this.activeFingerprint = null;
  }
}
