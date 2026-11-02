import { Focusable } from "@decky/ui";
import type { FC, ReactNode } from "react";

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

export const BAR_COLUMN = 64;

export const Bars: FC<{ value: number }> = ({ value }) => (
  <span style={{ display: "inline-flex", justifyContent: "center", gap: 2, width: BAR_COLUMN }}>
    {[1, 2, 3].map((n) => (
      <span key={n} style={{ width: 10, height: 4, borderRadius: 2, background: "currentColor", opacity: n <= value ? 0.9 : 0.25 }} />
    ))}
  </span>
);

export interface SegmentOption<T extends string> {
  value: T;
  label: string;
  caption?: ReactNode;
  icon?: ReactNode;
}

/** Panel's own segmented look (themes restyle it by its default values, so they are kept untouched). */
export function SegmentRow<T extends string>({ options, value, onChange, vertical = false }: {
  options: SegmentOption<T>[];
  value: T | null;
  onChange: (value: T) => void;
  vertical?: boolean;
}) {
  return (
    <Focusable
      flow-children={vertical ? "column" : "row"}
      style={{ ...segmentGroupStyle, display: "grid", gridTemplateColumns: vertical ? "1fr" : `repeat(${options.length}, 1fr)` }}
    >
      {options.map((option) => {
        const active = option.value === value;
        return (
          <Focusable
            key={option.value}
            onActivate={() => onChange(option.value)}
            onClick={() => onChange(option.value)}
            style={{
              ...segmentItemStyle(active),
              justifyContent: vertical ? "space-between" : "center",
              padding: `${theme.space.sm}px ${theme.space.sm}px`,
              whiteSpace: "normal",
              textAlign: vertical ? "left" : "center",
              lineHeight: 1.2,
            }}
          >
            <span style={{ display: "inline-flex", alignItems: "center", gap: theme.space.xs }}>{option.icon}{option.label}</span>
            {option.caption && <span style={{ fontSize: theme.font.caption, fontWeight: 400, opacity: 0.8, flexShrink: 0 }}>{option.caption}</span>}
          </Focusable>
        );
      })}
    </Focusable>
  );
}

export const Label: FC<{ children: ReactNode; aside?: ReactNode }> = ({ children, aside }) => (
  <div style={{ ...theme.sectionLabel, margin: `${theme.space.md}px 0 ${theme.space.xs}px`, display: "flex", alignItems: "baseline" }}>
    <span style={{ flex: 1 }}>{children}</span>
    {aside}
  </div>
);

export const Note: FC<{ children: ReactNode; tone?: "warn" | "danger" }> = ({ children, tone }) => (
  <div style={{
    fontSize: theme.font.caption, lineHeight: 1.35,
    color: tone === "danger" ? theme.color.danger : tone === "warn" ? theme.color.warn : theme.color.textMuted,
  }}>
    {children}
  </div>
);

export const Row: FC<{ children: ReactNode }> = ({ children }) => (
  <Focusable flow-children="row" style={{ display: "flex", gap: theme.space.xs }}>{children}</Focusable>
);

/** A Panel card used as a button: themes turn this exact style into their keys. */
export const ActionButton: FC<{
  label: string;
  onPress: () => void;
  primary?: boolean;
  danger?: boolean;
  busy?: boolean;
  disabled?: boolean;
}> = ({ label, onPress, primary, danger, busy, disabled }) => (
  <Focusable
    onActivate={disabled || busy ? undefined : onPress}
    onClick={disabled || busy ? undefined : onPress}
    style={{
      ...theme.card,
      ...(primary ? { background: theme.color.accent, boxShadow: "none" } : {}),
      flex: "1 1 0", minWidth: 0, padding: `${theme.space.sm}px ${theme.space.xs}px`,
      color: primary ? theme.color.onAccent : danger ? theme.color.danger : theme.color.textPrimary,
      fontWeight: 600, fontSize: theme.font.body, textAlign: "center",
      opacity: disabled ? 0.45 : 1, display: "flex", alignItems: "center", justifyContent: "center", gap: theme.space.xs,
      cursor: "pointer",
    }}
  >
    {busy && <Spinner size={12} />}
    {label}
  </Focusable>
);
