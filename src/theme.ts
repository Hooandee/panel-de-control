// PdC UI design tokens - the shared visual language for every Panel de Control screen.
// Keep this lightweight (no CSS-in-JS lib): plain objects consumed via inline styles.
const color = {
  surface: "#060608",
  surfaceRaised: "#0c0c10",
  hairline: "rgba(255,255,255,0.06)",
  textPrimary: "rgba(255,255,255,0.92)",
  textMuted: "rgba(255,255,255,0.45)",
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
} as const;

const radius = { sm: 8, md: 14, lg: 20 } as const;
const space = { xs: 4, sm: 8, md: 12, lg: 18 } as const;
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
} as const;
