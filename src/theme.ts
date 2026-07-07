// PdC UI design tokens - the shared visual language for every Panel de Control screen.
// Keep this lightweight (no CSS-in-JS lib): plain objects consumed via inline styles.
const color = {
  surface: "#060608",
  surfaceRaised: "#0c0c10",
  hairline: "rgba(255,255,255,0.06)",
  textPrimary: "rgba(255,255,255,0.92)",
  textMuted: "rgba(255,255,255,0.45)",
  // Signature blue. Also the color of every card/section TITLE icon (the icon
  // beside a card heading) — the one exception is a "green" feature card
  // (eco/learning/adaptive), whose title icon uses `ok`. Semantic status icons
  // (charging bolt, temperature, conflict warning) keep their own meaning color.
  accent: "#4ea1ff",
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
  brightness: "#f5c542",
} as const;

const radius = { sm: 8, md: 14, lg: 20 } as const;
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
    borderRadius: radius.md,
    background: color.surfaceRaised,
    boxShadow: `inset 0 0 0 1px ${color.hairline}`,
  },
  // Equal-width tile inside a card (fan chip, temp stat) — hairline-outlined,
  // shares one definition so side-by-side tiles can't drift apart.
  tile: {
    flex: "1 1 0",
    minWidth: 0,
    padding: space.sm,
    borderRadius: radius.sm,
    boxShadow: `inset 0 0 0 1px ${color.hairline}`,
  },
  // Muted uppercase caption used as a section heading inside the full-screen
  // modals (Customize, Glossary). Shared so the treatment stays consistent.
  sectionLabel: {
    fontSize: font.caption,
    color: color.textMuted,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
} as const;
