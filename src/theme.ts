import { currentAccentHex, currentAccentRgb, getAccentId } from "./system/accentColor";
import { getThemeTokensVersion, themeColorOverride, themeLabelTransform, themeRadiusOverride, themeSizeOverride } from "./system/themeTokens";

// PdC UI design tokens - the shared visual language for every Panel de Control screen.
// Keep this lightweight (no CSS-in-JS lib): plain objects consumed via inline styles.
const color = {
  surface: "#060608",
  surfaceRaised: "#0c0c10",
  hairline: "rgba(255,255,255,0.06)",
  textPrimary: "rgba(255,255,255,0.92)",
  textMuted: "rgba(255,255,255,0.45)",
  // Signature accent, user-selectable (a getter → the live hex). Also the colour of
  // every card/section TITLE icon; the exception is a "green" feature card
  // (eco/learning/adaptive), whose title icon uses `ok`.
  get accent(): string {
    return currentAccentHex();
  },
  // The accent as "r,g,b" for rgba() tints.
  get accentRgb(): string {
    return currentAccentRgb();
  },
  // Text/icon color on top of `accent` (e.g. the Apply button label) — a deep
  // navy so light-on-accent stays legible without a pure-black hard edge.
  onAccent: "#06121f",
  warn: "#ffb454",
  ok: "#7ee0a0",
  // Hot/over-limit red (thermal scale "limit" zone) — beyond `warn`/`boost`.
  danger: "#e05a5a",
  // Warm/bright orange for the transient HW-boost segment on the power arc — a
  // hotter tone than `warn` so it reads as "extra on top", not a warning.
  boost: "#ff8a3d",
  // Manual TDP requests outside the range Panel de Control stands behind.
  extra: "#b98cff",
  extraLow: "#8fd8ff",
  brightness: "#f5c542",
} as const;

const radius = { sm: 8, md: 14, lg: 20 } as const;

// Surfaces, text, radii and selection can be restyled by the active CSS Loader theme
// (./system/themeTokens); the values above stay Panel's own look.
const themedColor = Object.create(color, {
  surface: { enumerable: true, get: () => themeColorOverride("surface") ?? color.surface },
  surfaceRaised: { enumerable: true, get: () => themeColorOverride("surfaceRaised") ?? color.surfaceRaised },
  hairline: { enumerable: true, get: () => themeColorOverride("hairline") ?? color.hairline },
  // The edge of a card, tile or idle chip; dividers and gauge tracks keep `hairline`.
  outline: { enumerable: true, get: () => themeColorOverride("outline") ?? themedColor.hairline },
  textPrimary: { enumerable: true, get: () => themeColorOverride("textPrimary") ?? color.textPrimary },
  textMuted: { enumerable: true, get: () => themeColorOverride("textMuted") ?? color.textMuted },
  onAccent: { enumerable: true, get: () => themeColorOverride("onAccent") ?? color.onAccent },
  selectedFill: { enumerable: true, get: () => themeColorOverride("selectedFill") ?? color.accent },
  selectedText: { enumerable: true, get: () => themeColorOverride("selectedText") ?? themedColor.textPrimary },
}) as Omit<typeof color, "surface" | "surfaceRaised" | "hairline" | "textPrimary" | "textMuted" | "onAccent"> & {
  readonly surface: string;
  readonly surfaceRaised: string;
  readonly hairline: string;
  readonly outline: string;
  readonly textPrimary: string;
  readonly textMuted: string;
  readonly onAccent: string;
  readonly selectedFill: string;
  readonly selectedText: string;
};

const themedRadius = {
  get sm(): number {
    return themeRadiusOverride("sm") ?? radius.sm;
  },
  get md(): number {
    return themeRadiusOverride("md") ?? radius.md;
  },
  get lg(): number {
    return themeRadiusOverride("lg") ?? radius.lg;
  },
};
// `section` = the breathing gap BETWEEN stacked cards laid out in a flex column
// (shell chrome, settings rows). A touch more than `md` so containers read as
// separate, not glued. `card` = the bottom margin of a card that sits in its own
// PanelSectionRow (Decky adds a little vertical room; this makes cards breathe).
// Every card uses this ONE value so section gaps can't drift apart.
const space = { xs: 4, sm: 8, md: 12, lg: 18, section: 14, card: 6 } as const;
const font = { caption: 11, body: 13, value: 28 } as const;

export const theme = {
  color: themedColor,
  radius: themedRadius,
  space,
  font,
  get stroke(): number {
    return themeSizeOverride("stroke") ?? 1.5;
  },
  // Signature raised-surface style (bg + radius + hairline). Add padding per use.
  card: {
    get borderRadius(): number {
      return themedRadius.md;
    },
    get background(): string {
      return themedColor.surfaceRaised;
    },
    get boxShadow(): string {
      return `inset 0 0 0 1px ${themedColor.outline}`;
    },
  },
  // Equal-width tile inside a card (fan chip, temp stat) — hairline-outlined,
  // shares one definition so side-by-side tiles can't drift apart.
  tile: {
    flex: "1 1 0",
    minWidth: 0,
    padding: space.sm,
    get borderRadius(): number {
      return themedRadius.sm;
    },
    get boxShadow(): string {
      return `inset 0 0 0 1px ${themedColor.outline}`;
    },
  },
  // Muted uppercase caption used as a section heading inside the full-screen
  // modals (Customize, Glossary). Shared so the treatment stays consistent.
  sectionLabel: {
    fontSize: font.caption,
    get color(): string {
      return themedColor.textMuted;
    },
    get textTransform(): string {
      return themeLabelTransform() ?? "uppercase";
    },
    get letterSpacing(): number {
      return (themeLabelTransform() ?? "uppercase") === "uppercase" ? 0.5 : 0;
    },
  },
} as const;

/** A module-level style object that follows the live accent and theme tokens: rebuilt when
 *  either changes. Its keys are fixed by the first build; each one reads the live value. */
export function themed<T extends object>(build: () => T): T {
  let key = "";
  let value = build();
  const live = () => {
    const next = `${getAccentId()}|${getThemeTokensVersion()}`;
    if (next !== key) {
      key = next;
      value = build();
    }
    return value;
  };
  const object = {} as T;
  for (const prop of Reflect.ownKeys(value)) {
    Object.defineProperty(object, prop, { enumerable: true, get: () => Reflect.get(live(), prop) });
  }
  return object;
}
