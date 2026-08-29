import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ThemeActivator } from "./activation";
import { LOCAL_THEME_CATALOG } from "./catalog";
import { CssLoaderAdapter } from "./cssLoaderAdapter";
import type { CssLoaderSnapshot } from "./cssLoaderTypes";
import { createDeckyCssLoaderHost } from "./deckyCssLoaderHost";
import { deriveThemeCards, type ThemeCardModel } from "./state";
import type { ThemeCatalog } from "./types";
import type { CssLoaderApiInstallSource } from "./types";
import { THEME_RUNTIME_CHANGED_EVENT } from "./runtime/runtimeWatcher";

export interface ThemesAdapter {
  inspect(): Promise<CssLoaderSnapshot>;
  setPatchValue(themeName: string, patchName: string, value: string): Promise<CssLoaderSnapshot>;
  installTheme(source: CssLoaderApiInstallSource, expectedThemeName: string): Promise<CssLoaderSnapshot>;
}

export interface ThemesActivator {
  activate(themeId: string): Promise<CssLoaderSnapshot>;
}

export interface ThemesDependencies {
  catalog: ThemeCatalog;
  adapter: ThemesAdapter;
  activator: ThemesActivator;
  notifyRuntime?(): void;
}

export type ThemesOperation =
  | { kind: "installing"; themeId: string }
  | { kind: "activating"; themeId: string }
  | { kind: "saving"; themeId: string; patchName: string };

export interface ThemesController {
  loading: boolean;
  snapshot: CssLoaderSnapshot;
  cards: ThemeCardModel[];
  operation: ThemesOperation | null;
  error: string | null;
  refresh(): Promise<void>;
  install(themeId: string): Promise<boolean>;
  activate(themeId: string): Promise<boolean>;
  setPatch(themeId: string, patchName: string, value: string): Promise<boolean>;
}

let productionDependencies: ThemesDependencies | undefined;

function createProductionDependencies(): ThemesDependencies {
  if (productionDependencies) return productionDependencies;
  const minimumBackendVersion = Math.max(...LOCAL_THEME_CATALOG.themes
    .map((theme) => theme.minimumCssLoaderBackendVersion));
  const adapter = new CssLoaderAdapter(createDeckyCssLoaderHost(), { minimumBackendVersion });
  productionDependencies = {
    catalog: LOCAL_THEME_CATALOG,
    adapter,
    activator: new ThemeActivator(adapter, LOCAL_THEME_CATALOG),
    notifyRuntime: () => window.dispatchEvent(new Event(THEME_RUNTIME_CHANGED_EVENT)),
  };
  return productionDependencies;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Theme operation failed";
}

export function useThemes(dependencies?: ThemesDependencies): ThemesController {
  const deps = dependencies ?? createProductionDependencies();
  const [snapshot, setSnapshot] = useState<CssLoaderSnapshot>({ status: "missing", themes: [] });
  const [loading, setLoading] = useState(true);
  const [operation, setOperation] = useState<ThemesOperation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);
  const requestSequence = useRef(0);
  const operationLocked = useRef(false);

  useEffect(() => () => {
    mounted.current = false;
  }, []);

  const publishSnapshot = useCallback((request: number, value: CssLoaderSnapshot) => {
    if (!mounted.current || request !== requestSequence.current) return;
    setSnapshot(value);
    setError(null);
  }, []);

  const refresh = useCallback(async () => {
    const request = ++requestSequence.current;
    if (mounted.current) setLoading(true);
    try {
      publishSnapshot(request, await deps.adapter.inspect());
    } catch (refreshError) {
      if (mounted.current && request === requestSequence.current) {
        setError(errorMessage(refreshError));
      }
    } finally {
      if (mounted.current && request === requestSequence.current) setLoading(false);
    }
  }, [deps.adapter, publishSnapshot]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const activate = useCallback(async (themeId: string): Promise<boolean> => {
    if (operationLocked.current) return false;
    operationLocked.current = true;
    const request = ++requestSequence.current;
    if (mounted.current) {
      setOperation({ kind: "activating", themeId });
      setError(null);
    }
    try {
      const verified = await deps.activator.activate(themeId);
      publishSnapshot(request, verified);
      deps.notifyRuntime?.();
      return true;
    } catch (activationError) {
      if (mounted.current && request === requestSequence.current) {
        setError(errorMessage(activationError));
      }
      return false;
    } finally {
      operationLocked.current = false;
      if (mounted.current && request === requestSequence.current) setOperation(null);
    }
  }, [deps.activator, publishSnapshot]);

  const install = useCallback(async (themeId: string): Promise<boolean> => {
    if (operationLocked.current) return false;
    const entry = deps.catalog.themes.find((theme) => theme.id === themeId);
    if (!entry?.installSource) return false;
    operationLocked.current = true;
    const request = ++requestSequence.current;
    if (mounted.current) {
      setOperation({ kind: "installing", themeId });
      setError(null);
    }
    try {
      publishSnapshot(
        request,
        await deps.adapter.installTheme(entry.installSource, entry.cssLoaderName),
      );
      return true;
    } catch (installError) {
      if (mounted.current && request === requestSequence.current) {
        setError(errorMessage(installError));
      }
      return false;
    } finally {
      operationLocked.current = false;
      if (mounted.current && request === requestSequence.current) setOperation(null);
    }
  }, [deps.adapter, deps.catalog, publishSnapshot]);

  const setPatch = useCallback(async (
    themeId: string,
    patchName: string,
    value: string,
  ): Promise<boolean> => {
    if (operationLocked.current) return false;
    const entry = deps.catalog.themes.find((theme) => theme.id === themeId);
    if (!entry) return false;
    operationLocked.current = true;
    const request = ++requestSequence.current;
    if (mounted.current) {
      setOperation({ kind: "saving", themeId, patchName });
      setError(null);
    }
    try {
      const verified = await deps.adapter.setPatchValue(entry.cssLoaderName, patchName, value);
      publishSnapshot(
        request,
        verified,
      );
      deps.notifyRuntime?.();
      return true;
    } catch (patchError) {
      if (mounted.current && request === requestSequence.current) {
        setError(errorMessage(patchError));
      }
      return false;
    } finally {
      operationLocked.current = false;
      if (mounted.current && request === requestSequence.current) setOperation(null);
    }
  }, [deps.adapter, deps.catalog, publishSnapshot]);

  const cards = useMemo(
    () => deriveThemeCards(deps.catalog, snapshot),
    [deps.catalog, snapshot],
  );

  return { loading, snapshot, cards, operation, error, refresh, install, activate, setPatch };
}
