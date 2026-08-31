import type { CssLoaderSnapshot, CssLoaderTheme } from "./cssLoaderTypes";
import type {
  PublishedThemeRelease,
  ThemePublicationCompatibility,
  ThemePublicationState,
} from "./remotePublication";
import type { ThemeCatalog, ThemeCatalogEntry } from "./types";

export interface ThemeCardModel {
  id: string;
  catalog: ThemeCatalogEntry;
  installed: boolean;
  active: boolean;
  installedVersion?: string;
  publishedVersion?: string;
  publicationCompatibility?: ThemePublicationCompatibility;
  releaseNotes?: PublishedThemeRelease["notes"];
  targetVersion?: string;
  preferredInstallSource: "bundled" | "official-remote" | null;
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

function parseSemanticVersion(value: string): SemanticVersion | null {
  const match = /^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$/.exec(value);
  if (!match) return null;
  return {
    major: BigInt(match[1]),
    minor: BigInt(match[2]),
    patch: BigInt(match[3]),
    prerelease: match[4]?.split(".") ?? [],
  };
}

function comparePrereleaseIdentifier(left: string, right: string): number {
  const leftNumber = /^\d+$/.test(left) ? BigInt(left) : null;
  const rightNumber = /^\d+$/.test(right) ? BigInt(right) : null;
  if (leftNumber !== null && rightNumber !== null) {
    if (leftNumber < rightNumber) return -1;
    if (leftNumber > rightNumber) return 1;
    return 0;
  }
  if (leftNumber !== null) return -1;
  if (rightNumber !== null) return 1;
  return left.localeCompare(right, "en");
}

function compareSemanticVersions(leftValue: string, rightValue: string): number | null {
  const left = parseSemanticVersion(leftValue);
  const right = parseSemanticVersion(rightValue);
  if (!left || !right) return null;
  for (const key of ["major", "minor", "patch"] as const) {
    if (left[key] < right[key]) return -1;
    if (left[key] > right[key]) return 1;
  }
  if (left.prerelease.length === 0 || right.prerelease.length === 0) {
    if (left.prerelease.length === right.prerelease.length) return 0;
    return left.prerelease.length > 0 ? -1 : 1;
  }
  const length = Math.max(left.prerelease.length, right.prerelease.length);
  for (let index = 0; index < length; index += 1) {
    if (left.prerelease[index] === undefined) return -1;
    if (right.prerelease[index] === undefined) return 1;
    const comparison = comparePrereleaseIdentifier(left.prerelease[index], right.prerelease[index]);
    if (comparison !== 0) return comparison;
  }
  return 0;
}

function publishedThemes(
  publication: ThemePublicationState,
): Map<string, PublishedThemeRelease> {
  return publication.status === "published"
    ? new Map(publication.themes.map((release) => [release.catalogId, release]))
    : new Map();
}

export function deriveThemeCards(
  catalog: ThemeCatalog,
  snapshot: CssLoaderSnapshot,
  publication: ThemePublicationState = { status: "unchecked" },
): ThemeCardModel[] {
  const installed = snapshot.status === "ready"
    ? new Map(snapshot.themes.map((theme) => [theme.name, theme]))
    : new Map<string, CssLoaderTheme>();
  const published = publishedThemes(publication);
  return catalog.themes.map((entry) => {
    const cssLoaderTheme = installed.get(entry.cssLoaderName);
    const candidate = published.get(entry.id);
    const release = candidate?.cssLoaderName === entry.cssLoaderName ? candidate : undefined;
    const hasBundled = entry.includedVersion !== undefined
      && entry.installSources.some((source) => source.kind === "bundled");
    const hasCompatibleRemote = release?.compatibility === "compatible"
      && entry.installSources.some((source) => source.kind === "official-remote");
    let targetVersion = hasBundled ? entry.includedVersion : undefined;
    let preferredInstallSource: ThemeCardModel["preferredInstallSource"] = hasBundled
      ? "bundled"
      : null;
    if (
      hasCompatibleRemote
      && (cssLoaderTheme !== undefined || !hasBundled)
      && (
        targetVersion === undefined
        || (compareSemanticVersions(targetVersion, release.publishedVersion) ?? -1) < 0
      )
    ) {
      targetVersion = release.publishedVersion;
      preferredInstallSource = "official-remote";
    }
    const comparison = cssLoaderTheme && targetVersion
      ? compareSemanticVersions(cssLoaderTheme.version, targetVersion)
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
      id: entry.id,
      catalog: entry,
      installed: cssLoaderTheme !== undefined,
      active: cssLoaderTheme?.enabled ?? false,
      ...(cssLoaderTheme ? {
        installedVersion: cssLoaderTheme.version,
        cssLoaderTheme,
      } : {}),
      ...(release ? {
        publishedVersion: release.publishedVersion,
        publicationCompatibility: release.compatibility,
        releaseNotes: release.notes,
      } : {}),
      ...(targetVersion ? { targetVersion } : {}),
      preferredInstallSource,
      versionRelation,
      updateAvailable: versionRelation === "update-available",
    };
  });
}
