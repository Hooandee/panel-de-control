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
  "performance-budget",
] as const;

export type ThemeRuntimeCapability = typeof THEME_RUNTIME_CAPABILITIES[number];

export interface CssLoaderApiInstallSource {
  kind: "css-loader-api";
  baseUrl: string;
  themeId: string;
}

export interface ThemeRuntimeDeclaration {
  moduleId: string;
  surfaces: readonly ThemeRuntimeSurface[];
  capabilities: readonly ThemeRuntimeCapability[];
}

export interface ThemeCatalogEntry {
  id: string;
  cssLoaderName: string;
  name: string;
  descriptionKey: string;
  author: string;
  version: string;
  cssLoaderManifestVersion: number;
  minimumCssLoaderBackendVersion: number;
  projectUrl?: string;
  tags: readonly string[];
  exclusiveGroup?: string;
  runtime?: ThemeRuntimeDeclaration;
  installSource?: CssLoaderApiInstallSource;
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
