// A CSS Loader theme can restyle Panel de Control by publishing these custom properties on
// :root. Each one is read as a real value (not var()) so it also reaches SVG attributes and
// react-icons; anything missing or malformed keeps Panel's own look.
export const THEME_COLOR_TOKENS = {
  surface: "--pdc-theme-surface",
  surfaceRaised: "--pdc-theme-surface-raised",
  hairline: "--pdc-theme-hairline",
  textPrimary: "--pdc-theme-text",
  textMuted: "--pdc-theme-text-muted",
  onAccent: "--pdc-theme-on-accent",
} as const;

export const THEME_RADIUS_TOKENS = {
  sm: "--pdc-theme-radius-sm",
  md: "--pdc-theme-radius-md",
  lg: "--pdc-theme-radius-lg",
} as const;

export const THEME_SIZE_TOKENS = {
  stroke: "--pdc-theme-stroke",
} as const;

export type ThemeColorToken = keyof typeof THEME_COLOR_TOKENS;
export type ThemeRadiusToken = keyof typeof THEME_RADIUS_TOKENS;
export type ThemeSizeToken = keyof typeof THEME_SIZE_TOKENS;
export interface ThemeTokens {
  color: Partial<Record<ThemeColorToken, string>>;
  radius: Partial<Record<ThemeRadiusToken, number>>;
  size?: Partial<Record<ThemeSizeToken, number>>;
}

const HEX = /^#(?:[0-9a-f]{3}|[0-9a-f]{4}|[0-9a-f]{6}|[0-9a-f]{8})$/i;
const FUNCTIONAL = /^rgba?\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*(?:,\s*(?:0|1|0?\.\d+)\s*)?\)$/i;

export function parseThemeColor(value: string | null | undefined): string | null {
  const v = (value ?? "").trim();
  return HEX.test(v) || FUNCTIONAL.test(v) ? v : null;
}

export function parseThemeRadius(value: string | null | undefined): number | null {
  const m = /^(\d{1,2}(?:\.\d+)?)(?:px)?$/.exec((value ?? "").trim());
  return m ? Number(m[1]) : null;
}

export function readThemeTokens(doc: Document): ThemeTokens {
  const tokens: ThemeTokens = { color: {}, radius: {}, size: {} };
  const root = doc.documentElement;
  const view = doc.defaultView;
  if (!root || !view) return tokens;
  const style = view.getComputedStyle(root);
  for (const [name, property] of Object.entries(THEME_COLOR_TOKENS) as [ThemeColorToken, string][]) {
    const color = parseThemeColor(style.getPropertyValue(property));
    if (color) tokens.color[name] = color;
  }
  for (const [name, property] of Object.entries(THEME_RADIUS_TOKENS) as [ThemeRadiusToken, string][]) {
    const radius = parseThemeRadius(style.getPropertyValue(property));
    if (radius !== null) tokens.radius[name] = radius;
  }
  for (const [name, property] of Object.entries(THEME_SIZE_TOKENS) as [ThemeSizeToken, string][]) {
    const size = parseThemeRadius(style.getPropertyValue(property));
    if (size !== null) tokens.size![name] = size;
  }
  return tokens;
}

let current: ThemeTokens = { color: {}, radius: {} };
let version = 0;
const listeners = new Set<() => void>();

export function applyThemeTokens(next: ThemeTokens): void {
  if (JSON.stringify(next) === JSON.stringify(current)) return;
  current = next;
  version++;
  listeners.forEach((l) => l());
}

export function themeColorOverride(name: ThemeColorToken): string | undefined {
  return current.color[name];
}

export function themeRadiusOverride(name: ThemeRadiusToken): number | undefined {
  return current.radius[name];
}

export function themeSizeOverride(name: ThemeSizeToken): number | undefined {
  return current.size?.[name];
}

export function getThemeTokensVersion(): number {
  return version;
}

export function subscribeThemeTokens(cb: () => void): () => void {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}
