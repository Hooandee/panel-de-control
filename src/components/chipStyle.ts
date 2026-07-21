import { CSSProperties } from "react";
import { theme } from "../theme";

/** Shared icon-chip style for the arc's preset / firmware-mode buttons. */
export const iconChipStyle = (active: boolean): CSSProperties => ({
  flex: 1,
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  gap: 2,
  padding: "6px 4px",
  borderRadius: theme.radius.sm,
  background: active ? `rgba(${theme.color.accentRgb},0.18)` : theme.color.surfaceRaised,
  boxShadow: `inset 0 0 0 ${active ? 1.5 : 1}px ${active ? theme.color.accent : theme.color.hairline}`,
  color: active ? theme.color.accent : theme.color.textPrimary,
  fontSize: theme.font.caption,
  cursor: "pointer",
});
