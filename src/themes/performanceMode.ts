import type { CssLoaderPatch, CssLoaderTheme } from "./cssLoaderTypes";

// Reserved CSS Loader option a theme ships to offer a static, effect-free variant. An older Panel
// just shows it as one more checkbox, so declaring it never breaks an install there.
export const PERFORMANCE_PATCH = "Modo rendimiento";
export const PERFORMANCE_ON = "Yes";
export const PERFORMANCE_OFF = "No";
export const PERFORMANCE_MODE_KEY = "pdc:themePerformanceMode";

export interface PerformanceModeStore {
  // null until the choice is made in Panel.
  read(): boolean | null;
  write(on: boolean): void;
}

export interface PerformancePatchRef {
  themeName: string;
  patchName: typeof PERFORMANCE_PATCH;
  value: typeof PERFORMANCE_ON | typeof PERFORMANCE_OFF;
}

export function isPerformancePatch(patch: CssLoaderPatch): boolean {
  return patch.name === PERFORMANCE_PATCH
    && patch.type === "checkbox"
    && patch.options.includes(PERFORMANCE_ON)
    && patch.options.includes(PERFORMANCE_OFF);
}

export function supportsPerformanceMode(theme: CssLoaderTheme): boolean {
  return theme.patches.some(isPerformancePatch);
}

export function performanceValueOf(theme: CssLoaderTheme): string | undefined {
  return theme.patches.find(isPerformancePatch)?.value;
}

// Before Panel offered the switch, an older Panel showed the option as a plain checkbox; adopt
// what was ticked there instead of silently undoing it.
export function inheritedPerformanceMode(
  themes: readonly CssLoaderTheme[],
  hooandeeThemeNames: ReadonlySet<string>,
): boolean {
  return themes.some((theme) => hooandeeThemeNames.has(theme.name)
    && theme.patches.some((patch) => isPerformancePatch(patch) && patch.value === PERFORMANCE_ON));
}

export function planPerformanceMode(
  themes: readonly CssLoaderTheme[],
  hooandeeThemeNames: ReadonlySet<string>,
  on: boolean,
): PerformancePatchRef[] {
  const value = on ? PERFORMANCE_ON : PERFORMANCE_OFF;
  return themes
    .filter((theme) => hooandeeThemeNames.has(theme.name))
    .filter((theme) => theme.patches.some((patch) => isPerformancePatch(patch) && patch.value !== value))
    .map((theme) => ({ themeName: theme.name, patchName: PERFORMANCE_PATCH, value }));
}
