import type { CssLoaderSnapshot, CssLoaderTheme } from "./cssLoaderTypes";
import type { ThemeCatalog, ThemeCatalogEntry } from "./types";

export interface ThemeCardModel {
  id: string;
  catalog: ThemeCatalogEntry;
  installed: boolean;
  active: boolean;
  installedVersion?: string;
  updateAvailable: boolean;
  cssLoaderTheme?: CssLoaderTheme;
}

interface SemanticVersion {
  major: number;
  minor: number;
  patch: number;
  prerelease?: string;
}

function parseSemanticVersion(value: string): SemanticVersion | null {
  const match = /^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$/.exec(value);
  if (!match) return null;
  return {
    major: Number(match[1]),
    minor: Number(match[2]),
    patch: Number(match[3]),
    ...(match[4] ? { prerelease: match[4] } : {}),
  };
}

function isOlderVersion(installed: string, catalog: string): boolean {
  const left = parseSemanticVersion(installed);
  const right = parseSemanticVersion(catalog);
  if (!left || !right) return false;
  for (const key of ["major", "minor", "patch"] as const) {
    if (left[key] !== right[key]) return left[key] < right[key];
  }
  return left.prerelease !== undefined && right.prerelease === undefined;
}

export function deriveThemeCards(
  catalog: ThemeCatalog,
  snapshot: CssLoaderSnapshot,
): ThemeCardModel[] {
  const installed = snapshot.status === "ready"
    ? new Map(snapshot.themes.map((theme) => [theme.name, theme]))
    : new Map<string, CssLoaderTheme>();
  return catalog.themes.map((entry) => {
    const cssLoaderTheme = installed.get(entry.cssLoaderName);
    return {
      id: entry.id,
      catalog: entry,
      installed: cssLoaderTheme !== undefined,
      active: cssLoaderTheme?.enabled ?? false,
      ...(cssLoaderTheme ? {
        installedVersion: cssLoaderTheme.version,
        cssLoaderTheme,
      } : {}),
      updateAvailable: cssLoaderTheme
        ? isOlderVersion(cssLoaderTheme.version, entry.version)
        : false,
    };
  });
}
