import type { CssLoaderSnapshot, CssLoaderTheme } from "./cssLoaderTypes";
import type { PublishedThemeRelease, ThemePublicationState } from "./remotePublication";

export interface ThemeCardModel {
  id: string;
  release: PublishedThemeRelease;
  installed: boolean;
  active: boolean;
  installedVersion?: string;
  targetVersion?: string;
  installable: boolean;
  versionRelation: "not-installed" | "current" | "update-available" | "local-newer" | "unknown";
  updateAvailable: boolean;
  cssLoaderTheme?: CssLoaderTheme;
}

interface SemanticVersion {
  major: bigint;
  minor: bigint;
  patch: bigint;
  prerelease: string[];
}

const SEMANTIC_VERSION = /^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$/;

function parseSemanticVersion(value: string): SemanticVersion | null {
  const match = SEMANTIC_VERSION.exec(value);
  if (!match) return null;
  return {
    major: BigInt(match[1]),
    minor: BigInt(match[2]),
    patch: BigInt(match[3]),
    prerelease: match[4]?.split(".") ?? [],
  };
}

function compareIdentifier(left: string, right: string): number {
  const numeric = /^\d+$/;
  const leftNumber = numeric.test(left) ? BigInt(left) : null;
  const rightNumber = numeric.test(right) ? BigInt(right) : null;
  if (leftNumber !== null && rightNumber !== null) return leftNumber < rightNumber ? -1 : leftNumber > rightNumber ? 1 : 0;
  if (leftNumber !== null) return -1;
  if (rightNumber !== null) return 1;
  return left.localeCompare(right, "en");
}

function compareVersions(leftValue: string, rightValue: string): number | null {
  const left = parseSemanticVersion(leftValue);
  const right = parseSemanticVersion(rightValue);
  if (!left || !right) return null;
  for (const key of ["major", "minor", "patch"] as const) {
    if (left[key] < right[key]) return -1;
    if (left[key] > right[key]) return 1;
  }
  if (left.prerelease.length === 0 || right.prerelease.length === 0) {
    return left.prerelease.length === right.prerelease.length ? 0 : left.prerelease.length ? -1 : 1;
  }
  for (let index = 0; index < Math.max(left.prerelease.length, right.prerelease.length); index += 1) {
    if (left.prerelease[index] === undefined) return -1;
    if (right.prerelease[index] === undefined) return 1;
    const comparison = compareIdentifier(left.prerelease[index], right.prerelease[index]);
    if (comparison !== 0) return comparison;
  }
  return 0;
}

function usableThemes(publication: ThemePublicationState): readonly PublishedThemeRelease[] {
  return publication.status === "published" || publication.status === "cached"
    ? publication.themes
    : [];
}

export function deriveThemeCards(
  publication: ThemePublicationState,
  snapshot: CssLoaderSnapshot,
): ThemeCardModel[] {
  const installed = snapshot.status === "ready"
    ? new Map(snapshot.themes.map((theme) => [theme.name, theme]))
    : new Map<string, CssLoaderTheme>();
  return usableThemes(publication).map((release) => {
    const cssLoaderTheme = installed.get(release.cssLoaderName);
    const installable = release.compatibility === "compatible";
    const targetVersion = installable ? release.publishedVersion : undefined;
    const comparison = cssLoaderTheme && targetVersion
      ? compareVersions(cssLoaderTheme.version, targetVersion)
      : null;
    const versionRelation: ThemeCardModel["versionRelation"] = !cssLoaderTheme
      ? "not-installed"
      : !targetVersion || comparison === null
        ? "unknown"
        : comparison < 0
          ? "update-available"
          : comparison > 0
            ? "local-newer"
            : "current";
    return {
      id: release.catalogId,
      release,
      installed: cssLoaderTheme !== undefined,
      active: cssLoaderTheme?.enabled ?? false,
      installable,
      versionRelation,
      updateAvailable: versionRelation === "update-available",
      ...(cssLoaderTheme ? { installedVersion: cssLoaderTheme.version, cssLoaderTheme } : {}),
      ...(targetVersion ? { targetVersion } : {}),
    };
  });
}
