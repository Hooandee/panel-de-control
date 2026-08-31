export const THEME_RUNTIME_SURFACES = [
  "library",
  "library-grid",
  "game-details",
  "settings",
] as const;

export type ThemeRuntimeSurface = typeof THEME_RUNTIME_SURFACES[number];

export const THEME_RUNTIME_CAPABILITIES = [
  "orbital-library",
  "grid-motion",
  "adaptive-backdrop",
  "surface-styles",
  "details-transition",
  "settings-shell",
  "surface-isolation",
  "performance-budget",
] as const;

export type ThemeRuntimeCapability = typeof THEME_RUNTIME_CAPABILITIES[number];

export interface BundledThemeInstallSource {
  kind: "bundled";
  packageId: string;
}

export interface OfficialRemoteThemeInstallSource {
  kind: "official-remote";
  channelId: "panel-pages-v1";
}

export type ThemeInstallSource =
  | BundledThemeInstallSource
  | OfficialRemoteThemeInstallSource;

export type ThemeInstallRequest =
  | BundledThemeInstallSource
  | (OfficialRemoteThemeInstallSource & {
    catalogId: string;
    expectedVersion: string;
  });

export type ThemeAvailability = "available" | "coming-soon";

export interface ThemeRuntimeDeclaration {
  moduleId: string;
  surfaces: readonly ThemeRuntimeSurface[];
  capabilities: readonly ThemeRuntimeCapability[];
}

export interface ThemeCatalogEntry {
  id: string;
  cssLoaderName: string;
  nameKey: string;
  descriptionKey: string;
  availability: ThemeAvailability;
  author: string;
  includedVersion?: string;
  cssLoaderManifestVersion: number;
  minimumCssLoaderBackendVersion: number;
  projectUrl?: string;
  tags: readonly string[];
  exclusiveGroup?: string;
  runtime?: ThemeRuntimeDeclaration;
  installSources: readonly ThemeInstallSource[];
}

export interface ThemeCatalog {
  schemaVersion: 1;
  themes: readonly ThemeCatalogEntry[];
}

export interface ThemeCatalogIssue {
  path: string;
  code: "invalid" | "invalid_url" | "duplicate" | "unsupported";
  message: string;
}

export type ThemeCatalogValidation =
  | { ok: true; catalog: ThemeCatalog }
  | { ok: false; issues: ThemeCatalogIssue[] };
