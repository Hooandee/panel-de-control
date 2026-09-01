export const THEME_RUNTIME_SURFACES = [
  "library",
  "library-grid",
  "game-details",
  "settings",
] as const;

export type ThemeRuntimeSurface = typeof THEME_RUNTIME_SURFACES[number];

export interface ThemeInstallRequest {
  kind: "official-remote";
  channelId: "panel-pages-v1";
  catalogId: string;
  expectedVersion: string;
}
