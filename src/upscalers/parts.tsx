import { Focusable } from "@decky/ui";
import { useState, type FC, type ReactNode } from "react";

import { segmentGroupStyle, segmentItemStyle } from "../components/segmented";
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

export const Chip: FC<{ children: ReactNode }> = ({ children }) => (
  <span style={{
    fontSize: theme.font.caption, fontWeight: 700, padding: "1px 7px", borderRadius: 999, flexShrink: 0,
    color: theme.color.textPrimary, boxShadow: `inset 0 0 0 1px ${theme.color.outline}`, background: theme.color.hairline,
  }}>
    {children}
  </span>
);

export const Bars: FC<{ value: number; label: string }> = ({ value, label }) => (
  <span style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: theme.font.caption, fontWeight: 400 }}>
    <span style={{ display: "inline-flex", gap: 2 }}>
      {[1, 2, 3].map((n) => (
        <span key={n} style={{ width: 8, height: 4, borderRadius: 2, background: "currentColor", opacity: n <= value ? 0.9 : 0.25 }} />
      ))}
    </span>
    {label}
  </span>
);

export interface SegmentOption<T extends string> {
  value: T;
  label: string;
  caption?: ReactNode;
  icon?: ReactNode;
}

/** The shared segmented look (themes map it to their own keys); options may carry a caption line. */
export function SegmentRow<T extends string>({ options, value, onChange }: {
  options: SegmentOption<T>[];
  value: T | null;
  onChange: (value: T) => void;
}) {
  return (
    <Focusable flow-children="row" style={{ ...segmentGroupStyle, display: "grid", gridTemplateColumns: `repeat(${options.length}, 1fr)` }}>
      {options.map((option) => {
        const active = option.value === value;
        return (
          <Focusable
            key={option.value}
            onActivate={() => onChange(option.value)}
            onClick={() => onChange(option.value)}
            style={{
              ...segmentItemStyle(active),
              flexDirection: "column",
              gap: 2,
              padding: `${theme.space.sm}px ${theme.space.xs}px`,
              color: active ? theme.color.selectedText : theme.color.textPrimary,
              whiteSpace: "normal",
              textAlign: "center",
            }}
          >
            {option.icon}
            <span>{option.label}</span>
            {option.caption && <span style={{ fontSize: theme.font.caption, fontWeight: 400, opacity: 0.75 }}>{option.caption}</span>}
          </Focusable>
        );
      })}
    </Focusable>
  );
}

export const Label: FC<{ children: ReactNode }> = ({ children }) => (
  <div style={{ ...theme.sectionLabel, margin: `${theme.space.md}px 0 ${theme.space.xs}px` }}>{children}</div>
);

export const Note: FC<{ children: ReactNode; color?: string }> = ({ children, color }) => (
  <div style={{ display: "flex", gap: theme.space.xs, alignItems: "baseline", fontSize: theme.font.caption + 1, color: theme.color.textMuted }}>
    {color && <Dot color={color} />}
    <span style={{ color: color ? theme.color.textPrimary : undefined }}>{children}</span>
  </div>
);

export const Row: FC<{ children: ReactNode }> = ({ children }) => (
  <Focusable flow-children="row" style={{ display: "flex", gap: theme.space.xs }}>{children}</Focusable>
);

export const ActionButton: FC<{
  label: string;
  onPress: () => void;
  primary?: boolean;
  danger?: boolean;
  busy?: boolean;
  disabled?: boolean;
  grow?: boolean;
}> = ({ label, onPress, primary, danger, busy, disabled, grow = true }) => {
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
        flex: grow ? "1 1 0" : "0 0 auto", padding: `${theme.space.sm}px ${theme.space.md}px`, borderRadius: theme.radius.sm,
        background: fill, color, fontWeight: 600, fontSize: theme.font.body, textAlign: "center",
        boxShadow: focused ? `0 0 0 2px ${theme.color.textPrimary}` : primary ? "none" : `inset 0 0 0 1px ${theme.color.outline}`,
        opacity: disabled ? 0.45 : 1, display: "flex", alignItems: "center", justifyContent: "center", gap: theme.space.xs,
        cursor: disabled ? "default" : "pointer", whiteSpace: "nowrap",
      }}
    >
      {busy && <Spinner size={12} />}
      {label}
    </Focusable>
  );
};
