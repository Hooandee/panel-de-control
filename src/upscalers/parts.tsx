import { Focusable } from "@decky/ui";
import { useState, type CSSProperties, type FC, type ReactNode } from "react";

import { theme } from "../theme";
import type { UpscalerStatus } from "./types";

export const MOTION_CSS = `
@keyframes pdc-up-spin { to { transform: rotate(360deg); } }
@keyframes pdc-up-shimmer { 0% { opacity: .35; } 50% { opacity: .7; } 100% { opacity: .35; } }
@keyframes pdc-up-in { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) {
  [data-pdc-up-motion] { animation: none !important; transition: none !important; }
}`;

export const statusColor = (status: UpscalerStatus | null): string => {
  switch (status) {
    case "active": return theme.color.ok;
    case "broken": return theme.color.danger;
    case "loaded":
    case "pending":
    case "not_run": return theme.color.accent;
    default: return theme.color.textMuted;
  }
};

export const Spinner: FC<{ size?: number }> = ({ size = 14 }) => (
  <span
    data-pdc-up-motion
    style={{
      width: size, height: size, flexShrink: 0, borderRadius: "50%",
      border: `2px solid ${theme.color.hairline}`, borderTopColor: theme.color.accent,
      animation: "pdc-up-spin 800ms linear infinite", display: "inline-block",
    }}
  />
);

export const Skeleton: FC<{ height: number; width?: string }> = ({ height, width = "100%" }) => (
  <div
    data-pdc-up-motion
    style={{
      height, width, borderRadius: theme.radius.sm, background: theme.color.hairline,
      animation: "pdc-up-shimmer 1.2s ease-in-out infinite",
    }}
  />
);

export const Dot: FC<{ color: string }> = ({ color }) => (
  <span style={{ width: 8, height: 8, borderRadius: 4, background: color, flexShrink: 0, display: "inline-block" }} />
);

export const Pips: FC<{ value: number; glyph: string }> = ({ value, glyph }) => (
  <span style={{ letterSpacing: 1, fontSize: theme.font.caption }}>
    {[1, 2, 3].map((n) => (
      <span key={n} style={{ opacity: n <= value ? 1 : 0.25 }}>{glyph}</span>
    ))}
  </span>
);

/** A selectable card; `disabled` keeps it visible and focusable so its reason can be read. */
export const ChoiceCard: FC<{
  selected: boolean;
  disabled?: boolean;
  onPick: () => void;
  style?: CSSProperties;
  children: ReactNode;
}> = ({ selected, disabled, onPick, style, children }) => {
  const [focused, setFocused] = useState(false);
  const ring = focused
    ? `inset 0 0 0 2px ${theme.color.accent}`
    : selected
      ? `inset 0 0 0 1.5px ${theme.color.accent}`
      : theme.card.boxShadow;
  return (
    <Focusable
      onActivate={disabled ? undefined : onPick}
      onClick={disabled ? undefined : onPick}
      onGamepadFocus={() => setFocused(true)}
      onGamepadBlur={() => setFocused(false)}
      data-pdc-up-motion
      style={{
        flex: "1 1 0", minWidth: 0, padding: theme.space.sm, borderRadius: theme.radius.sm,
        background: selected ? `${theme.color.accent}22` : theme.color.surfaceRaised,
        boxShadow: ring, opacity: disabled ? 0.45 : 1, cursor: disabled ? "default" : "pointer",
        display: "flex", flexDirection: "column", gap: 2, transition: "background 120ms ease, box-shadow 120ms ease",
        ...style,
      }}
    >
      {children}
    </Focusable>
  );
};

export const Label: FC<{ children: ReactNode }> = ({ children }) => (
  <div style={{ ...theme.sectionLabel, margin: `${theme.space.md}px 0 ${theme.space.xs}px` }}>{children}</div>
);

export const Row: FC<{ children: ReactNode }> = ({ children }) => (
  <Focusable flow-children="horizontal" style={{ display: "flex", gap: theme.space.xs }}>{children}</Focusable>
);

export const ActionButton: FC<{
  label: string;
  onPress: () => void;
  primary?: boolean;
  danger?: boolean;
  busy?: boolean;
  disabled?: boolean;
}> = ({ label, onPress, primary, danger, busy, disabled }) => {
  const [focused, setFocused] = useState(false);
  const fill = primary ? theme.color.accent : "transparent";
  const color = primary ? theme.color.onAccent : danger ? theme.color.danger : theme.color.textPrimary;
  return (
    <Focusable
      onActivate={disabled || busy ? undefined : onPress}
      onClick={disabled || busy ? undefined : onPress}
      onGamepadFocus={() => setFocused(true)}
      onGamepadBlur={() => setFocused(false)}
      style={{
        flex: "1 1 0", padding: `${theme.space.sm}px ${theme.space.md}px`, borderRadius: theme.radius.sm,
        background: fill, color, fontWeight: 600, fontSize: theme.font.body, textAlign: "center",
        boxShadow: focused ? `0 0 0 2px ${theme.color.textPrimary}` : primary ? "none" : `inset 0 0 0 1px ${theme.color.outline}`,
        opacity: disabled ? 0.45 : 1, display: "flex", alignItems: "center", justifyContent: "center", gap: theme.space.xs,
        cursor: disabled ? "default" : "pointer",
      }}
    >
      {busy && <Spinner size={12} />}
      {label}
    </Focusable>
  );
};
