import { currentAccentHex, currentAccentRgb, getAccentId } from "./system/accentColor";
import { getThemeTokensVersion, themeColorOverride, themeRadiusOverride } from "./system/themeTokens";

// PdC UI design tokens - the shared visual language for every Panel de Control screen.
// Keep this lightweight (no CSS-in-JS lib): plain objects consumed via inline styles.
// Surfaces, text and radii can be restyled by the active CSS Loader theme (./system/themeTokens).
const color = {
  get surface(): string {
    return themeColorOverride("surface") ?? "#060608";
  },
  get surfaceRaised(): string {
    return themeColorOverride("surfaceRaised") ?? "#0c0c10";
  },
  get hairline(): string {
    return themeColorOverride("hairline") ?? "rgba(255,255,255,0.06)";
  },
  get textPrimary(): string {
    return themeColorOverride("textPrimary") ?? "rgba(255,255,255,0.92)";
  },
  get textMuted(): string {
    return themeColorOverride("textMuted") ?? "rgba(255,255,255,0.45)";
  },
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
  get onAccent(): string {
    return themeColorOverride("onAccent") ?? "#06121f";
  },
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

const radius = {
  get sm(): number {
    return themeRadiusOverride("sm") ?? 8;
  },
  get md(): number {
    return themeRadiusOverride("md") ?? 14;
  },
  get lg(): number {
    return themeRadiusOverride("lg") ?? 20;
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
  color,
  radius,
  space,
  font,
  // Signature raised-surface style (bg + radius + hairline). Add padding per use.
  card: {
    get borderRadius(): number {
      return radius.md;
    },
    get background(): string {
      return color.surfaceRaised;
    },
    get boxShadow(): string {
      return `inset 0 0 0 1px ${color.hairline}`;
    },
  },
  // Equal-width tile inside a card (fan chip, temp stat) — hairline-outlined,
  // shares one definition so side-by-side tiles can't drift apart.
  tile: {
    flex: "1 1 0",
    minWidth: 0,
    padding: space.sm,
    get borderRadius(): number {
      return radius.sm;
    },
    get boxShadow(): string {
      return `inset 0 0 0 1px ${color.hairline}`;
    },
  },
  // Muted uppercase caption used as a section heading inside the full-screen
  // modals (Customize, Glossary). Shared so the treatment stays consistent.
  sectionLabel: {
    fontSize: font.caption,
    get color(): string {
      return color.textMuted;
    },
    textTransform: "uppercase",
    letterSpacing: 0.5,
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
