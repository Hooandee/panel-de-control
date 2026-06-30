import { CSSProperties } from "react";
import { theme } from "../theme";

// Shared "segmented pill group" visual language (pattern A): a raised rounded
// group holding equal pills, the active one filled with the accent. Used by both
// the TabBar (control-center navigator) and the TDP ProfileSelector so the look
// is defined once and can't drift.

export const segmentGroupStyle: CSSProperties = {
  display: "flex",
  gap: 4,
  padding: 4,
  ...theme.card,
};

export function segmentItemStyle(active: boolean): CSSProperties {
  return {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 5,
    borderRadius: theme.radius.sm,
    fontSize: theme.font.body,
    fontWeight: active ? 600 : 400,
    color: active ? theme.color.textPrimary : theme.color.textMuted,
    background: active ? theme.color.accent : "transparent",
    cursor: "pointer",
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
    transition: "background 140ms ease, color 140ms ease",
  };
}
