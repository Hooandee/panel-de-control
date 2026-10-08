import type { CssLoaderSnapshot } from "./cssLoaderTypes";

export type ThemeFolderKind =
  | "hooandee"
  | "third_party"
  | "profile"
  | "legacy"
  | "broken"
  | "leftover"
  | "duplicate";

export const SET_ASIDE_KINDS: ReadonlySet<ThemeFolderKind> = new Set(["legacy", "broken", "leftover", "duplicate"]);

export interface ThemeFolder {
  folder: string;
  name: string;
  kind: ThemeFolderKind;
  active: boolean;
}

export interface ThemeHealthBackend {
  folders: ThemeFolder[];
  panel: { width: number; height: number } | null;
  undo: { available: boolean; moved: number; disabled: number; error?: string };
}

export interface SteamDisplayState {
  scale: number | null;
  autoScale: number | null;
  usingAutoScale: boolean | null;
  external: boolean | null;
  beta: boolean | null;
  pixelRatio: number | null;
  width: number | null;
  height: number | null;
  cssLoaderStyles: number | null;
}

export type ThemeHealthSeverity = "problem" | "setting" | "info";

export type ThemeHealthFinding =
  | { id: "css_loader"; severity: "problem"; status: CssLoaderSnapshot["status"] }
  | { id: "other_active"; severity: "problem"; names: string[] }
  | { id: "profile_active"; severity: "problem"; names: string[] }
  | { id: "ghost_styles"; severity: "problem"; count: number }
  | { id: "set_aside"; severity: "problem"; folders: { folder: string; kind: ThemeFolderKind }[] }
  | { id: "several_hooandee"; severity: "info"; names: string[] }
  | { id: "steam_scale"; severity: "setting"; scale: number; autoScale: number }
  | { id: "resolution"; severity: "setting"; width: number; height: number; panelWidth: number; panelHeight: number }
  | { id: "external_display"; severity: "info" }
  | { id: "steam_beta"; severity: "setting" };

export interface ThemeCleanupPlan {
  keep: string[];
  disable: string[];
  setAside: number;
  ghostStyles: boolean;
}

const KINDS = new Set<ThemeFolderKind>([
  "hooandee", "third_party", "profile", "legacy", "broken", "leftover", "duplicate",
]);
const SCALE_TOLERANCE = 0.01;

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function flag(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

export function parseThemeHealth(raw: unknown): ThemeHealthBackend {
  const value = record(raw);
  if (!value || !Array.isArray(value.folders)) throw new Error("Theme health response is invalid");
  const folders = value.folders.flatMap((item): ThemeFolder[] => {
    const entry = record(item);
    if (
      !entry
      || typeof entry.folder !== "string"
      || typeof entry.name !== "string"
      || typeof entry.kind !== "string"
      || !KINDS.has(entry.kind as ThemeFolderKind)
      || typeof entry.active !== "boolean"
    ) {
      return [];
    }
    return [{ folder: entry.folder, name: entry.name, kind: entry.kind as ThemeFolderKind, active: entry.active }];
  });
  const panel = record(value.panel);
  const panelWidth = finiteNumber(panel?.width);
  const panelHeight = finiteNumber(panel?.height);
  const undo = record(value.undo);
  return {
    folders,
    panel: panelWidth && panelHeight ? { width: panelWidth, height: panelHeight } : null,
    undo: {
      available: undo?.available === true,
      moved: finiteNumber(undo?.moved) ?? 0,
      disabled: finiteNumber(undo?.disabled) ?? 0,
      ...(typeof undo?.error === "string" ? { error: undo.error } : {}),
    },
  };
}

interface SteamSettingsSnapshot {
  flCurrentDisplayScaleFactor?: unknown;
  flAutoDisplayScaleFactor?: unknown;
  bDisplayIsUsingAutoScale?: unknown;
  bDisplayIsExternal?: unknown;
  bIsInClientBeta?: unknown;
}

interface SteamSettingsApi {
  RegisterForSettingsChanges?: (callback: (settings: SteamSettingsSnapshot) => void) => { unregister?: () => void } | undefined;
}

// Steam answers the registration with the current settings; nothing arrives when the API is gone.
export function readSteamSettings(
  api: SteamSettingsApi | undefined,
  timeoutMs = 1_500,
): Promise<SteamSettingsSnapshot | null> {
  const register = api?.RegisterForSettingsChanges;
  if (typeof register !== "function") return Promise.resolve(null);
  return new Promise((resolve) => {
    let done = false;
    let handle: { unregister?: () => void } | undefined;
    const release = () => {
      try {
        handle?.unregister?.();
      } catch {}
    };
    const finish = (settings: SteamSettingsSnapshot | null) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      release();
      resolve(settings);
    };
    const timer = setTimeout(() => finish(null), timeoutMs);
    try {
      handle = register.call(api, (settings) => finish(record(settings) ? settings : null));
    } catch {
      finish(null);
    }
    if (done) release();
  });
}

const CSS_LOADER_STYLE = "style.css-loader-style";

export function countCssLoaderStyles(documents: readonly Document[]): number | null {
  let total: number | null = null;
  for (const document of documents) {
    try {
      total = (total ?? 0) + document.querySelectorAll(CSS_LOADER_STYLE).length;
    } catch {}
  }
  return total;
}

export function removeCssLoaderStyles(documents: readonly Document[]): number {
  let removed = 0;
  for (const document of documents) {
    try {
      document.querySelectorAll(CSS_LOADER_STYLE).forEach((style) => {
        style.remove();
        removed += 1;
      });
    } catch {}
  }
  return removed;
}

export function steamDisplayState(
  settings: SteamSettingsSnapshot | null,
  view: { devicePixelRatio?: number; innerWidth?: number; innerHeight?: number } | null,
  documents: readonly Document[] = [],
): SteamDisplayState {
  const pixelRatio = finiteNumber(view?.devicePixelRatio);
  const innerWidth = finiteNumber(view?.innerWidth);
  const innerHeight = finiteNumber(view?.innerHeight);
  const cssLoaderStyles = countCssLoaderStyles(documents);
  return {
    scale: finiteNumber(settings?.flCurrentDisplayScaleFactor),
    autoScale: finiteNumber(settings?.flAutoDisplayScaleFactor),
    usingAutoScale: flag(settings?.bDisplayIsUsingAutoScale),
    external: flag(settings?.bDisplayIsExternal),
    beta: flag(settings?.bIsInClientBeta),
    pixelRatio,
    width: pixelRatio && innerWidth ? Math.round(innerWidth * pixelRatio) : null,
    height: pixelRatio && innerHeight ? Math.round(innerHeight * pixelRatio) : null,
    cssLoaderStyles,
  };
}

export function displayReport(display: SteamDisplayState): Record<string, number | boolean | null> {
  return {
    scale: display.scale,
    auto_scale: display.autoScale,
    using_auto_scale: display.usingAutoScale,
    external: display.external,
    beta: display.beta,
    pixel_ratio: display.pixelRatio,
    width: display.width,
    height: display.height,
    css_loader_styles: display.cssLoaderStyles,
  };
}

export function hooandeeNames(backend: ThemeHealthBackend, catalogNames: Iterable<string>): Set<string> {
  return new Set([
    ...catalogNames,
    ...backend.folders.filter((folder) => folder.kind === "hooandee").map((folder) => folder.name),
  ]);
}

export function diagnoseThemeHealth(
  snapshot: CssLoaderSnapshot,
  backend: ThemeHealthBackend,
  display: SteamDisplayState,
  keep: ReadonlySet<string>,
): ThemeHealthFinding[] {
  const findings: ThemeHealthFinding[] = [];
  if (snapshot.status !== "ready") findings.push({ id: "css_loader", severity: "problem", status: snapshot.status });

  const profiles = new Set(backend.folders.filter((folder) => folder.kind === "profile").map((folder) => folder.name));
  const enabled = snapshot.themes.filter((theme) => theme.enabled);
  const foreign = enabled.filter((theme) => !keep.has(theme.name));
  const others = foreign.filter((theme) => !profiles.has(theme.name)).map((theme) => theme.displayName || theme.name);
  const activeProfiles = foreign.filter((theme) => profiles.has(theme.name)).map((theme) => theme.displayName || theme.name);
  if (others.length) findings.push({ id: "other_active", severity: "problem", names: others });
  if (activeProfiles.length) findings.push({ id: "profile_active", severity: "problem", names: activeProfiles });

  // With CSS Loader off or removed nothing owns its styles; while it runs, only an empty list proves it.
  const cssLoaderGone = snapshot.status === "missing" || snapshot.status === "disabled";
  if ((cssLoaderGone || (snapshot.status === "ready" && enabled.length === 0)) && (display.cssLoaderStyles ?? 0) > 0) {
    findings.push({ id: "ghost_styles", severity: "problem", count: display.cssLoaderStyles ?? 0 });
  }

  const setAside = backend.folders
    .filter((folder) => SET_ASIDE_KINDS.has(folder.kind))
    .map(({ folder, kind }) => ({ folder, kind }));
  if (setAside.length) findings.push({ id: "set_aside", severity: "problem", folders: setAside });

  const ours = enabled.filter((theme) => keep.has(theme.name));
  if (ours.length > 1) {
    findings.push({ id: "several_hooandee", severity: "info", names: ours.map((theme) => theme.displayName || theme.name) });
  }

  if (
    display.usingAutoScale === false
    && display.scale !== null
    && display.autoScale !== null
    && Math.abs(display.scale - display.autoScale) > SCALE_TOLERANCE
  ) {
    findings.push({ id: "steam_scale", severity: "setting", scale: display.scale, autoScale: display.autoScale });
  }

  if (display.external === true) {
    findings.push({ id: "external_display", severity: "info" });
  } else if (backend.panel && display.width !== null && display.height !== null) {
    const drawn = [display.width, display.height].sort((a, b) => b - a);
    const native = [backend.panel.width, backend.panel.height].sort((a, b) => b - a);
    // CEF rounds the CSS viewport up, so the drawn size can exceed the panel by up to one CSS pixel.
    const tolerance = Math.ceil(display.pixelRatio ?? 1);
    if (Math.abs(drawn[0] - native[0]) > tolerance || Math.abs(drawn[1] - native[1]) > tolerance) {
      findings.push({
        id: "resolution",
        severity: "setting",
        width: display.width,
        height: display.height,
        panelWidth: native[0],
        panelHeight: native[1],
      });
    }
  }

  if (display.beta === true) findings.push({ id: "steam_beta", severity: "setting" });
  return findings;
}

export function cleanupPlan(
  snapshot: CssLoaderSnapshot,
  findings: readonly ThemeHealthFinding[],
  keep: ReadonlySet<string>,
): ThemeCleanupPlan {
  const setAside = findings.find((finding) => finding.id === "set_aside");
  return {
    keep: [...keep],
    disable: snapshot.themes.filter((theme) => theme.enabled && !keep.has(theme.name)).map((theme) => theme.name),
    setAside: setAside?.id === "set_aside" ? setAside.folders.length : 0,
    ghostStyles: findings.some((finding) => finding.id === "ghost_styles"),
  };
}

export function cleanupNeeded(plan: ThemeCleanupPlan): boolean {
  return plan.disable.length > 0 || plan.setAside > 0 || plan.ghostStyles;
}
