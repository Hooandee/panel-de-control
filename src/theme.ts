// PdC UI design tokens - the shared visual language for every Panel de Control screen.
// Keep this lightweight (no CSS-in-JS lib): plain objects consumed via inline styles.
export const theme = {
  color: {
    surface: "#060608",
    surfaceRaised: "#0c0c10",
    hairline: "rgba(255,255,255,0.06)",
    textPrimary: "rgba(255,255,255,0.92)",
    textMuted: "rgba(255,255,255,0.45)",
    accent: "#4ea1ff",
    warn: "#ffb454",
  },
  radius: { sm: 8, md: 14, lg: 20 },
  space: { xs: 4, sm: 8, md: 12, lg: 18 },
  font: { caption: 11, body: 13, value: 28 },
} as const;
