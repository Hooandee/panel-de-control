import { useMemo, useSyncExternalStore } from "react";

import type { CssLoaderSnapshot } from "./cssLoaderTypes";
import type { ThemePublicationState } from "./remotePublication";
import { deriveThemeCards, type ThemeCardModel } from "./state";
import {
  createProductionThemesDependencies,
  ThemesClient,
  type ThemesDependencies,
  type ThemesOperation,
  type ThemeInstallConfirmation,
} from "./themesClient";

export type { ThemesAdapter, ThemesActivator, ThemesDependencies, ThemesOperation } from "./themesClient";

export interface ThemesController {
  loading: boolean;
  refreshing: boolean;
  snapshot: CssLoaderSnapshot;
  cards: ThemeCardModel[];
  operation: ThemesOperation | null;
  recoveryBlocked: boolean;
  error: string | null;
  publication: ThemePublicationState;
  refresh(): Promise<void>;
  refreshPublication(): Promise<void>;
  install(themeId: string, confirmation?: ThemeInstallConfirmation): Promise<boolean>;
  activate(themeId: string): Promise<boolean>;
  deactivate(themeId: string): Promise<boolean>;
  setPatch(themeId: string, patchName: string, value: string): Promise<boolean>;
}

const clients = new WeakMap<ThemesDependencies, ThemesClient>();

export function getThemesClient(dependencies: ThemesDependencies): ThemesClient {
  const existing = clients.get(dependencies);
  if (existing) return existing;
  const created = new ThemesClient(dependencies);
  clients.set(dependencies, created);
  return created;
}

export function useThemes(dependencies?: ThemesDependencies): ThemesController {
  const deps = dependencies ?? createProductionThemesDependencies();
  const client = useMemo(() => getThemesClient(deps), [deps]);
  const current = useSyncExternalStore(client.subscribe, client.getSnapshot, client.getSnapshot);

  const cards = useMemo(
    () => deriveThemeCards(current.publication, current.snapshot),
    [current.snapshot, current.publication],
  );

  return {
    ...current,
    cards,
    refresh: client.refresh,
    refreshPublication: client.refreshPublication,
    install: client.install,
    activate: client.activate,
    deactivate: client.deactivate,
    setPatch: client.setPatch,
  };
}
