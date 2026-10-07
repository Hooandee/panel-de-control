// User-selectable accent — pure core. theme.color.accent reads the getters here, so a
// real hex reaches CSS, SVG attributes and react-icons. No React/storage import so this
// stays a light leaf; the hook + durable persistence live in ./useAccent.

export interface Accent {
  id: string;
  hex: string;
}

export const ACCENTS: Accent[] = [
  { id: "blue", hex: "#4ea1ff" },
  { id: "sky", hex: "#38bdf8" },
  { id: "cyan", hex: "#22b8e0" },
  { id: "teal", hex: "#22c7c0" },
  { id: "mint", hex: "#34d399" },
  { id: "green", hex: "#3fbf6f" },
  { id: "lime", hex: "#a3d43f" },
  { id: "yellow", hex: "#f5c542" },
  { id: "amber", hex: "#e0952a" },
  { id: "orange", hex: "#f2683c" },
  { id: "red", hex: "#e5484d" },
  { id: "rose", hex: "#fb7185" },
  { id: "pink", hex: "#ec5c9d" },
  { id: "fuchsia", hex: "#d946ef" },
  { id: "purple", hex: "#9b7bf0" },
  { id: "indigo", hex: "#6366f1" },
];

export const DEFAULT_ACCENT = ACCENTS[0];
export const FALLBACK_ACCENT_RGB = "78,161,255";
// The selection that follows the active theme: a theme publishes its accent as
// `--pdc-theme-accent: r, g, b` and Panel falls back to DEFAULT_ACCENT without one.
export const THEME_ACCENT_ID = "default";

export function resolveAccent(id: string | null | undefined): Accent {
  return ACCENTS.find((a) => a.id === id) ?? DEFAULT_ACCENT;
}

export function resolveAccentSelection(id: string | null | undefined): string {
  return ACCENTS.some((a) => a.id === id) ? (id as string) : THEME_ACCENT_ID;
}

export function parseRgbTriplet(value: string | null | undefined): string | null {
  const parts = (value ?? "").trim().split(/\s*,\s*|\s+/).filter(Boolean);
  if (parts.length !== 3) return null;
  const channels = parts.map((part) => (/^\d{1,3}$/.test(part) ? Number(part) : NaN));
  if (channels.some((c) => !Number.isInteger(c) || c < 0 || c > 255)) return null;
  return channels.join(",");
}

export function rgbTripletToHex(triplet: string): string {
  return `#${triplet.split(",").map((c) => Number(c).toString(16).padStart(2, "0")).join("")}`;
}

export function hexToRgbTriplet(hex: string): string {
  const h = hex.replace(/^#/, "");
  if (!/^[0-9a-fA-F]{6}$/.test(h)) return FALLBACK_ACCENT_RGB;
  return `${parseInt(h.slice(0, 2), 16)},${parseInt(h.slice(2, 4), 16)},${parseInt(h.slice(4, 6), 16)}`;
}

// Cache the resolved hex/triplet so the theme getters (read every render) don't
// re-parse; recomputed only on change. Seeded from persistence by ./useAccent.
let selection = THEME_ACCENT_ID;
let themeRgb: string | null = null;
let current: Accent = DEFAULT_ACCENT;
let currentRgb = hexToRgbTriplet(current.hex);
const listeners = new Set<() => void>();

function recompute(): void {
  const next: Accent = selection !== THEME_ACCENT_ID
    ? resolveAccent(selection)
    : { id: THEME_ACCENT_ID, hex: themeRgb ? rgbTripletToHex(themeRgb) : DEFAULT_ACCENT.hex };
  if (next.id === current.id && next.hex === current.hex) return;
  current = next;
  currentRgb = hexToRgbTriplet(next.hex);
  listeners.forEach((l) => l());
}

export function getAccentId(): string {
  return `${current.id}:${current.hex}`;
}

export function getAccent(): Accent {
  return current;
}

export function applyAccentId(id: string | null | undefined): void {
  selection = resolveAccentSelection(id);
  recompute();
}

export function applyThemeAccent(value: string | null | undefined): void {
  themeRgb = parseRgbTriplet(value);
  recompute();
}

export function themeAccentHex(): string | null {
  return themeRgb ? rgbTripletToHex(themeRgb) : null;
}

export function subscribeAccent(cb: () => void): () => void {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

export function currentAccentHex(): string {
  return current.hex;
}

export function currentAccentRgb(): string {
  return currentRgb;
}
