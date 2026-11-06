import { Focusable } from "@decky/ui";
import { useRef, useState, type FC, type ReactNode } from "react";
import { LuCheck, LuChevronDown, LuChevronRight } from "react-icons/lu";

import { segmentGroupStyle, segmentItemStyle } from "../components/segmented";
import { createThemeNavigationAccess } from "../themes/runtime/navigationAccess";
import { theme } from "../theme";
import type { UpscalerStatus } from "./types";

const navigation = createThemeNavigationAccess({ allowInactiveContext: true });

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
              flexDirection: !vertical && option.caption ? "column" : "row",
              minWidth: 0,
              fontSize: !vertical && option.caption ? theme.font.caption - 1 : theme.font.body,
              gap: !vertical && option.caption ? 2 : 5,
              justifyContent: vertical ? "space-between" : "center",
              padding: `${theme.space.sm}px ${!vertical && option.caption ? 1 : theme.space.sm}px`,
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

export function PickerButton<T extends string>({ label, value, options, onChange, disabled, badge }: {
  label: string;
  value: T;
  options: { value: T; label: string; caption?: string }[];
  onChange: (value: T) => void;
  disabled?: boolean;
  badge?: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLDivElement>(null);
  const close = () => {
    setOpen(false);
    if (trigger.current) navigation.focus(trigger.current);
  };
  const current = options.find((o) => o.value === value)?.label ?? value;
  const toggle = () => { if (!disabled) setOpen(!open); };
  return (
    <div style={{ ...theme.card, minWidth: 0, overflow: "hidden", opacity: disabled ? 0.45 : 1 }}>
      <Focusable ref={trigger} role="button" aria-label={label} aria-expanded={open} aria-disabled={disabled}
        onActivate={toggle} onClick={toggle} onCancel={open ? (event) => { event.stopPropagation(); close(); } : undefined}
        style={{ padding: `${theme.space.sm}px ${theme.space.md}px`, display: "flex", alignItems: "center", gap: theme.space.xs, cursor: "pointer" }}>
        <span style={{ flex: 1, minWidth: 0, display: "flex", flexWrap: "wrap", alignItems: "center", gap: theme.space.xs,
          fontSize: theme.font.body, fontWeight: 600, color: theme.color.textPrimary, whiteSpace: "normal", overflowWrap: "anywhere" }}>
          {current}{badge}
        </span>
        <LuChevronDown size={16} color={theme.color.textMuted} style={{ flexShrink: 0, transform: open ? "rotate(180deg)" : undefined }} />
      </Focusable>
      {open && <Focusable role="radiogroup" aria-label={label} onCancel={(event) => { event.stopPropagation(); close(); }} flow-children="column" style={{ display: "flex", flexDirection: "column" }}>
        {options.map((option) => {
          const select = () => { if (!disabled) { close(); onChange(option.value); } };
          return <Focusable key={option.value} role="radio" aria-checked={option.value === value} aria-disabled={disabled}
            onActivate={select} onClick={select}
            style={{ display: "flex", alignItems: "flex-start", gap: theme.space.xs, padding: `${theme.space.sm}px ${theme.space.md}px`,
              borderTop: `1px solid ${theme.color.hairline}`, color: theme.color.textPrimary, fontSize: theme.font.body, whiteSpace: "normal", cursor: "pointer" }}>
            <span style={{ width: 16, flexShrink: 0, display: "flex", paddingTop: 2 }}>{option.value === value && <LuCheck size={14} />}</span>
            <span style={{ minWidth: 0, flex: 1, display: "flex", flexDirection: "column", gap: 4, overflowWrap: "anywhere", lineHeight: 1.35 }}>
              {option.label}
              {option.caption && <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{option.caption}</span>}
            </span>
          </Focusable>;
        })}
      </Focusable>}
    </div>
  );
}

/** A card note led by an icon, never a colour dot. */
export const Notice: FC<{ icon: ReactNode; children: ReactNode; tone?: "warn" | "danger" }> = ({ icon, children, tone }) => (
  <div style={{
    ...theme.card, padding: `${theme.space.sm + 2}px ${theme.space.md}px`, display: "flex", alignItems: "flex-start", gap: theme.space.sm,
    fontSize: theme.font.caption + 1, lineHeight: 1.35,
    color: tone === "danger" ? theme.color.danger : tone === "warn" ? theme.color.warn : theme.color.textMuted,
  }}>
    <span style={{ display: "inline-flex", flexShrink: 0, marginTop: 1 }}>{icon}</span>
    <span style={{ flex: 1 }}>{children}</span>
  </div>
);

export const ListCard: FC<{ children: ReactNode }> = ({ children }) => (
  <Focusable flow-children="column" style={{ ...theme.card, padding: 0, overflow: "hidden", display: "flex", flexDirection: "column" }}>
    {children}
  </Focusable>
);

const Switch: FC<{ on: boolean }> = ({ on }) => (
  <span style={{
    width: 38, height: 22, borderRadius: 20, position: "relative", flexShrink: 0,
    background: on ? theme.color.accent : "rgba(255,255,255,0.14)",
  }}>
    <span style={{
      position: "absolute", top: 2, [on ? "right" : "left"]: 2, width: 18, height: 18, borderRadius: "50%",
      background: on ? theme.color.onAccent : "rgba(255,255,255,0.55)",
    }} />
  </span>
);

/** One line of a ListCard: a switch, a value, or a chevron that opens something. */
export const ListRow: FC<{
  label: string;
  onPress?: () => void;
  detail?: ReactNode;
  caption?: string;
  on?: boolean;
  chevron?: boolean;
  danger?: boolean;
  busy?: boolean;
  disabled?: boolean;
  first?: boolean;
}> = ({ label, onPress, detail, caption, on, chevron, danger, busy, disabled, first }) => {
  const press = disabled || busy || !onPress ? undefined : onPress;
  return (
    <Focusable
      role={on === undefined ? undefined : "switch"}
      aria-checked={on}
      onActivate={press}
      onClick={press}
      style={{
        display: "flex", alignItems: "center", gap: theme.space.sm, padding: `${theme.space.sm + 3}px ${theme.space.md}px`,
        borderTop: first ? "none" : `1px solid ${theme.color.hairline}`, opacity: disabled ? 0.45 : 1, cursor: "pointer",
      }}
    >
      <span style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 2 }}>
        <span style={{ fontSize: theme.font.body, color: danger ? theme.color.danger : theme.color.textPrimary, fontWeight: danger ? 600 : 400 }}>{label}</span>
        {caption && <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{caption}</span>}
      </span>
      {busy && <Spinner size={12} />}
      {detail !== undefined && <span style={{ fontSize: theme.font.caption + 1, color: theme.color.textMuted, textAlign: "right" }}>{detail}</span>}
      {on !== undefined && <Switch on={on} />}
      {chevron && <LuChevronRight size={16} color={theme.color.textMuted} />}
    </Focusable>
  );
};

export const Fold: FC<{ label: string; open: boolean; onToggle: () => void }> = ({ label, open, onToggle }) => (
  <Focusable
    aria-expanded={open}
    onActivate={onToggle}
    onClick={onToggle}
    style={{
      ...theme.card, padding: `${theme.space.sm + 3}px ${theme.space.md}px`, display: "flex", alignItems: "center",
      fontSize: theme.font.body, color: theme.color.textMuted, cursor: "pointer",
    }}
  >
    <span style={{ flex: 1 }}>{label}</span>
    {open ? <LuChevronDown size={16} /> : <LuChevronRight size={16} />}
  </Focusable>
);
