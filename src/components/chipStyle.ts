import { CSSProperties } from "react";
import { theme } from "../theme";

/** Shared accent/hairline chip visual (active vs idle). Layout is added per use. */
const chipVisual = (active: boolean): CSSProperties => ({
  borderRadius: theme.radius.sm,
  background: active ? `rgba(${theme.color.accentRgb},0.18)` : theme.color.surfaceRaised,
  boxShadow: `inset 0 0 0 ${active ? 1.5 : 1}px ${active ? theme.color.accent : theme.color.hairline}`,
  color: active ? theme.color.accent : theme.color.textPrimary,
  fontSize: theme.font.caption,
  cursor: "pointer",
});

/** Equal-width column chip (icon over label) for the arc's preset / firmware-mode grid. */
export const iconChipStyle = (active: boolean): CSSProperties => ({
  ...chipVisual(active),
  flex: 1,
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  gap: 2,
  padding: "6px 4px",
});

/** Compact row chip (icon + label inline) for wrapping chip rows. */
export const rowChipStyle = (active: boolean): CSSProperties => ({
  ...chipVisual(active),
  display: "flex",
  alignItems: "center",
  gap: 5,
  padding: "6px 9px",
});
