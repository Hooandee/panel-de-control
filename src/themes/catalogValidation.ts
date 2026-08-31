import {
  THEME_RUNTIME_CAPABILITIES,
  THEME_RUNTIME_SURFACES,
  ThemeCatalog,
  ThemeCatalogIssue,
  ThemeCatalogValidation,
} from "./types";

const RUNTIME_SURFACES = new Set<string>(THEME_RUNTIME_SURFACES);
const RUNTIME_CAPABILITIES = new Set<string>(THEME_RUNTIME_CAPABILITIES);
const SEMVER = /^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function nonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function positiveInteger(value: unknown): value is number {
  return Number.isInteger(value) && (value as number) > 0;
}

function isHttpsUrl(value: unknown): boolean {
  if (!nonEmptyString(value)) return false;
  try {
    return new URL(value).protocol === "https:";
  } catch {
    return false;
  }
}

function validateRuntime(
  runtime: unknown,
  path: string,
  issues: ThemeCatalogIssue[],
): void {
  if (runtime === undefined) return;
  if (!isRecord(runtime)) {
    issues.push({ path, code: "invalid", message: "Runtime declaration must be an object" });
    return;
  }
  if (!nonEmptyString(runtime.moduleId)) {
    issues.push({ path: `${path}.moduleId`, code: "invalid", message: "Runtime module id is required" });
  }
  if (!Array.isArray(runtime.surfaces)) {
    issues.push({ path: `${path}.surfaces`, code: "invalid", message: "Runtime surfaces must be an array" });
  } else {
    runtime.surfaces.forEach((surface, index) => {
      if (!nonEmptyString(surface) || !RUNTIME_SURFACES.has(surface)) {
        issues.push({
          path: `${path}.surfaces[${index}]`,
          code: "unsupported",
          message: `Unsupported runtime surface: ${String(surface)}`,
        });
      }
    });
  }
  if (!Array.isArray(runtime.capabilities)) {
    issues.push({ path: `${path}.capabilities`, code: "invalid", message: "Runtime capabilities must be an array" });
  } else {
    runtime.capabilities.forEach((capability, index) => {
      if (!nonEmptyString(capability) || !RUNTIME_CAPABILITIES.has(capability)) {
        issues.push({
          path: `${path}.capabilities[${index}]`,
          code: "unsupported",
          message: `Unsupported runtime capability: ${String(capability)}`,
        });
      }
    });
  }
}

function validateInstallSource(
  source: unknown,
  path: string,
  issues: ThemeCatalogIssue[],
  catalogId: unknown,
): void {
  if (!isRecord(source)) {
    issues.push({ path, code: "unsupported", message: "Unsupported install source" });
    return;
  }
  if (source.kind === "official-remote") {
    for (const field of Object.keys(source)) {
      if (field !== "kind" && field !== "channelId") {
        issues.push({
          path: `${path}.${field}`,
          code: "unsupported",
          message: `Install source contains an unsupported field: ${field}`,
        });
      }
    }
    if (source.channelId !== "panel-pages-v1") {
      issues.push({
        path: `${path}.channelId`,
        code: "unsupported",
        message: "Unsupported official theme channel",
      });
    }
    return;
  }
  if (source.kind !== "bundled") {
    issues.push({ path, code: "unsupported", message: "Unsupported install source" });
    return;
  }
  for (const field of Object.keys(source)) {
    if (field !== "kind" && field !== "packageId") {
      issues.push({
        path: `${path}.${field}`,
        code: "unsupported",
        message: `Install source contains an unsupported field: ${field}`,
      });
    }
  }
  if (!nonEmptyString(source.packageId) || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(source.packageId)) {
    issues.push({
      path: `${path}.packageId`,
      code: "invalid",
      message: "Bundled package id must be a stable slug",
    });
  } else if (source.packageId !== catalogId) {
    issues.push({
      path: `${path}.packageId`,
      code: "invalid",
      message: "Bundled package id must match its catalog id",
    });
  }
}

export function validateThemeCatalog(input: unknown): ThemeCatalogValidation {
  const issues: ThemeCatalogIssue[] = [];
  if (!isRecord(input) || input.schemaVersion !== 1 || !Array.isArray(input.themes)) {
    return {
      ok: false,
      issues: [{ path: "catalog", code: "invalid", message: "Catalog schema is invalid" }],
    };
  }

  const ids = new Set<string>();
  const cssLoaderNames = new Set<string>();
  input.themes.forEach((theme, index) => {
    const path = `themes[${index}]`;
    if (!isRecord(theme)) {
      issues.push({ path, code: "invalid", message: "Theme entry must be an object" });
      return;
    }

    if (!nonEmptyString(theme.id)) {
      issues.push({ path: `${path}.id`, code: "invalid", message: "Theme id is required" });
    } else if (ids.has(theme.id)) {
      issues.push({ path: `${path}.id`, code: "duplicate", message: `Duplicate theme id: ${theme.id}` });
    } else {
      ids.add(theme.id);
    }

    if (!nonEmptyString(theme.cssLoaderName)) {
      issues.push({ path: `${path}.cssLoaderName`, code: "invalid", message: "CSS Loader name is required" });
    } else if (cssLoaderNames.has(theme.cssLoaderName)) {
      issues.push({
        path: `${path}.cssLoaderName`,
        code: "duplicate",
        message: `Duplicate CSS Loader name: ${theme.cssLoaderName}`,
      });
    } else {
      cssLoaderNames.add(theme.cssLoaderName);
    }

    for (const field of ["nameKey", "descriptionKey", "author"] as const) {
      if (!nonEmptyString(theme[field])) {
        issues.push({ path: `${path}.${field}`, code: "invalid", message: `${field} is required` });
      }
    }
    if (theme.includedVersion !== undefined && (
      !nonEmptyString(theme.includedVersion) || !SEMVER.test(theme.includedVersion)
    )) {
      issues.push({
        path: `${path}.includedVersion`,
        code: "invalid",
        message: "Included theme version must use semantic versioning",
      });
    }
    if (!positiveInteger(theme.cssLoaderManifestVersion)) {
      issues.push({ path: `${path}.cssLoaderManifestVersion`, code: "invalid", message: "CSS Loader manifest version is invalid" });
    }
    if (!positiveInteger(theme.minimumCssLoaderBackendVersion)) {
      issues.push({ path: `${path}.minimumCssLoaderBackendVersion`, code: "invalid", message: "Minimum CSS Loader backend version is invalid" });
    }
    if (!Array.isArray(theme.tags) || theme.tags.some((tag) => !nonEmptyString(tag))) {
      issues.push({ path: `${path}.tags`, code: "invalid", message: "Theme tags must be non-empty strings" });
    }
    if (theme.projectUrl !== undefined && !isHttpsUrl(theme.projectUrl)) {
      issues.push({ path: `${path}.projectUrl`, code: "invalid_url", message: "Project URL must use HTTPS" });
    }
    if (theme.exclusiveGroup !== undefined && !nonEmptyString(theme.exclusiveGroup)) {
      issues.push({ path: `${path}.exclusiveGroup`, code: "invalid", message: "Exclusive group must be a non-empty string" });
    }
    if (theme.availability !== "available" && theme.availability !== "coming-soon") {
      issues.push({
        path: `${path}.availability`,
        code: "unsupported",
        message: `Unsupported theme availability: ${String(theme.availability)}`,
      });
    }

    if (!Array.isArray(theme.installSources)) {
      issues.push({
        path: `${path}.installSources`,
        code: "invalid",
        message: "Theme install sources must be an array",
      });
    } else {
      const sourceKinds = new Set<string>();
      theme.installSources.forEach((source, sourceIndex) => {
        const sourcePath = `${path}.installSources[${sourceIndex}]`;
        validateInstallSource(source, sourcePath, issues, theme.id);
        if (isRecord(source) && nonEmptyString(source.kind)) {
          if (sourceKinds.has(source.kind)) {
            issues.push({
              path: sourcePath,
              code: "duplicate",
              message: `Duplicate install source: ${source.kind}`,
            });
          }
          sourceKinds.add(source.kind);
        }
      });
      const hasBundledSource = theme.installSources.some((source) => (
        isRecord(source) && source.kind === "bundled"
      ));
      if (hasBundledSource && theme.includedVersion === undefined) {
        issues.push({
          path: `${path}.includedVersion`,
          code: "invalid",
          message: "Bundled themes must declare their included version",
        });
      } else if (!hasBundledSource && theme.includedVersion !== undefined) {
        issues.push({
          path: `${path}.includedVersion`,
          code: "invalid",
          message: "Only bundled themes can declare an included version",
        });
      }
      if (theme.availability === "coming-soon" && theme.installSources.length > 0) {
        issues.push({
          path: `${path}.installSources`,
          code: "invalid",
          message: "Coming-soon themes cannot declare install sources",
        });
      }
    }

    validateRuntime(theme.runtime, `${path}.runtime`, issues);
  });

  return issues.length > 0
    ? { ok: false, issues }
    : { ok: true, catalog: input as unknown as ThemeCatalog };
}
