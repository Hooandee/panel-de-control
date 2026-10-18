export const THEME_RUNTIME_SURFACES = [
  "library",
  "library-grid",
  "game-details",
  "settings",
] as const;

export type ThemeRuntimeSurface = typeof THEME_RUNTIME_SURFACES[number];

export type ThemeInstallRequest =
  | {
    kind: "official-remote";
    channelId: "panel-pages-v1";
    catalogId: string;
    expectedVersion: string;
  }
  // A zip the user picked; the backend installs it only if it is a published early build.
  | { kind: "early-archive"; catalogId: string; archivePath: string };
