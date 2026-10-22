import { FC } from "react";

import { theme } from "../theme";

export const OnPanelDot: FC = () => (
  <span style={{ width: 7, height: 7, borderRadius: 4, background: theme.color.ok, flex: "0 0 auto", boxShadow: `0 0 6px ${theme.color.ok}` }} />
);

export const tileStyle = (focused: boolean, selected: boolean) => ({
  borderRadius: theme.radius.md,
  padding: theme.space.sm,
  display: "flex",
  flexDirection: "column" as const,
  alignItems: "center",
  gap: theme.space.xs + 2,
  minWidth: 0,
  background: selected ? `rgba(${theme.color.accentRgb},0.14)` : theme.color.surfaceRaised,
  boxShadow: focused
    ? `inset 0 0 0 2px ${theme.color.accent}, 0 0 0 2px ${theme.color.accent}, 0 6px 18px rgba(0,0,0,0.45)`
    : selected ? `inset 0 0 0 2px ${theme.color.accent}aa` : `inset 0 0 0 1px ${theme.color.outline}`,
  transform: focused ? "scale(1.04)" : "scale(1)",
  transition: "box-shadow 120ms ease, transform 120ms ease, background 160ms ease",
});

