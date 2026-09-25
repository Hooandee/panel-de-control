export type ThemeGameLaunchResult = "started" | "unavailable" | "failed";

const LIBRARY_DETAILS_LAUNCH_SOURCE = 100;

export interface ThemeExtensionLibraryAccess {
  launch(appId: number): ThemeGameLaunchResult;
  openSettings(appId: number): boolean;
  openController(appId: number): boolean;
  verticalCapsule(appId: number): string | null;
}

interface GameOverview {
  appid?: number;
  gameid?: string;
  m_gameid?: string;
  library_capsule_filename?: string | null;
  local_cache_version?: number | string | null;
}

interface ThemeLibraryDependencies {
  getOverview(appId: number): GameOverview | null | undefined;
  runGame?(gameId: string): void;
  openSettings?(appId: number): void;
  openController?(appId: number): void;
  customVerticalCapsules?(overview: GameOverview): readonly unknown[] | null | undefined;
}

const LOCAL_CAPSULE_FILENAME = /^(?:[0-9a-f]+\/)?[\w.-]+\.(?:jpe?g|png|webp)$/i;

function localImagePath(value: unknown): string | null {
  return typeof value === "string" && value.startsWith("/") && !value.startsWith("//") ? value : null;
}

function customVerticalCapsule(dependencies: ThemeLibraryDependencies, overview: GameOverview): string | null {
  try {
    for (const url of dependencies.customVerticalCapsules?.(overview) ?? []) {
      const path = localImagePath(url);
      if (path) return path;
    }
  } catch {
    return null;
  }
  return null;
}

function steamVerticalCapsule(overview: GameOverview & { appid: number }): string | null {
  const filename = overview.library_capsule_filename;
  if (typeof filename !== "string" || !LOCAL_CAPSULE_FILENAME.test(filename)) return null;
  const version = overview.local_cache_version;
  const cache = version === null || version === undefined || version === "" ? "" : `?c=${encodeURIComponent(String(version))}`;
  return `/assets/${overview.appid}/${filename}${cache}`;
}

function validAppId(appId: number): boolean {
  return Number.isSafeInteger(appId) && appId > 0;
}

function matchingOverview(
  dependencies: ThemeLibraryDependencies,
  appId: number,
): GameOverview | null {
  if (!validAppId(appId)) return null;
  try {
    const overview = dependencies.getOverview(appId);
    return overview?.appid === appId ? overview : null;
  } catch {
    return null;
  }
}

function steamDependencies(): ThemeLibraryDependencies {
  const apps = typeof SteamClient === "undefined" ? undefined : SteamClient?.Apps;
  const runGame = typeof apps?.RunGame === "function"
    ? (gameId: string) => apps.RunGame(gameId, "", -1, LIBRARY_DETAILS_LAUNCH_SOURCE)
    : undefined;
  const openController = typeof apps?.ShowControllerConfigurator === "function"
    ? (appId: number) => apps.ShowControllerConfigurator(appId)
    : undefined;

  const store = window.appStore as unknown as {
    GetCustomVerticalCapsuleURLs?: (overview: GameOverview) => readonly unknown[];
  } | undefined;

  return {
    getOverview: (appId) => window.appStore?.GetAppOverviewByAppID?.(appId),
    customVerticalCapsules: typeof store?.GetCustomVerticalCapsuleURLs === "function"
      ? (overview) => store.GetCustomVerticalCapsuleURLs?.(overview)
      : undefined,
    runGame,
    openController,
    openSettings: (appId) => {
      const focused = window.SteamUIStore?.GetFocusedWindowInstance?.() as unknown as {
        Navigator?: { AppProperties?: (selectedAppId: number) => void };
      } | undefined;
      if (typeof focused?.Navigator?.AppProperties !== "function") {
        throw new Error("Steam app settings are unavailable");
      }
      focused.Navigator.AppProperties(appId);
    },
  };
}

export function createThemeLibraryAccess(
  dependencies: ThemeLibraryDependencies = steamDependencies(),
): Readonly<ThemeExtensionLibraryAccess> {
  return Object.freeze({
    launch(appId: number) {
      const overview = matchingOverview(dependencies, appId);
      const gameId = overview?.gameid ?? overview?.m_gameid;
      if (!gameId || !dependencies.runGame) return "unavailable";
      try {
        dependencies.runGame(gameId);
        return "started";
      } catch {
        return "failed";
      }
    },
    openSettings(appId: number) {
      if (!matchingOverview(dependencies, appId) || !dependencies.openSettings) return false;
      try {
        dependencies.openSettings(appId);
        return true;
      } catch {
        return false;
      }
    },
    openController(appId: number) {
      if (!matchingOverview(dependencies, appId) || !dependencies.openController) return false;
      try {
        dependencies.openController(appId);
        return true;
      } catch {
        return false;
      }
    },
    verticalCapsule(appId: number) {
      const overview = matchingOverview(dependencies, appId);
      if (!overview) return null;
      return customVerticalCapsule(dependencies, overview)
        ?? steamVerticalCapsule({ ...overview, appid: appId });
    },
  });
}
