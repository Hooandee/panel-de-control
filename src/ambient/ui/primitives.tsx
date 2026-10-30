import { Dropdown, Focusable, Menu, MenuItem, showContextMenu } from "@decky/ui";
import { useRef, useState, type CSSProperties, type FC, type ReactNode } from "react";
import { LuCheck, LuChevronDown, LuChevronRight, LuX } from "react-icons/lu";

import { ContainedSlider } from "../../components/ContainedSlider";
import type { OverlayCorner } from "../core/types";
import { isCollapsed, setCollapsed } from "../../platform/preferences";

import { theme } from "../../theme";

export const cardStyle: CSSProperties = {
  ...theme.card,
  padding: theme.space.md,
  display: "flex",
  flexDirection: "column",
  gap: theme.space.sm,
  marginBottom: theme.space.card,
};

export const CardTitle: FC<{ icon: ReactNode; title: string; trailing?: ReactNode; wrap?: boolean }> = ({ icon, title, trailing, wrap }) => (
  <div style={{ display: "flex", alignItems: wrap ? "flex-start" : "center", gap: theme.space.sm, fontSize: theme.font.body, fontWeight: 600, color: theme.color.textPrimary }}>
    <span style={{ color: theme.color.accent, display: "inline-flex", paddingTop: wrap ? 2 : 0 }}>{icon}</span>
    <span style={wrap
      ? { flex: 1, minWidth: 0, lineHeight: 1.3, textWrap: "balance" }
      : { flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{title}</span>
    {trailing && <span style={{ fontWeight: 400, fontSize: theme.font.caption, color: theme.color.textMuted, whiteSpace: "nowrap" }}>{trailing}</span>}
  </div>
);

export const Caption: FC<{ children: ReactNode; style?: CSSProperties }> = ({ children, style }) => (
  <div style={{ ...theme.sectionLabel, ...style }}>{children}</div>
);

export const Hairline: FC = () => <div style={{ height: 1, background: theme.color.hairline }} />;

export const Button: FC<{ label: ReactNode; primary?: boolean; onActivate: () => void; disabled?: boolean; style?: CSSProperties }> = ({ label, primary, onActivate, disabled, style }) => (
  <Focusable
    onActivate={disabled ? undefined : onActivate}
    onClick={disabled ? undefined : onActivate}
    style={{
      minHeight: 34,
      borderRadius: theme.radius.sm,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      gap: 6,
      padding: "6px 10px",
      boxSizing: "border-box",
      textAlign: "center",
      lineHeight: 1.2,
      fontSize: 12,
      fontWeight: 600,
      cursor: disabled ? "default" : "pointer",
      opacity: disabled ? 0.45 : 1,
      color: primary ? theme.color.onAccent : theme.color.textPrimary,
      background: primary ? theme.color.accent : "rgba(255,255,255,0.06)",
      boxShadow: primary ? "none" : `inset 0 0 0 1px ${theme.color.hairline}`,
      ...style,
    }}
  >
    {label}
  </Focusable>
);

export const Row: FC<{ swatch?: ReactNode; title: string; subtitle?: string; trailing?: ReactNode; selected?: boolean; onActivate?: () => void; onSecondary?: () => void }> = ({ swatch, title, subtitle, trailing, selected, onActivate, onSecondary }) => (
  <Focusable
    onActivate={onActivate}
    onClick={onActivate}
    onSecondaryButton={onSecondary}
    style={{
      display: "flex",
      alignItems: "center",
      gap: 10,
      padding: "7px 6px",
      borderRadius: theme.radius.sm,
      cursor: onActivate ? "pointer" : "default",
      background: selected ? `rgba(${theme.color.accentRgb},0.12)` : "transparent",
      boxShadow: selected ? `inset 0 0 0 1px rgba(${theme.color.accentRgb},0.4)` : "none",
    }}
  >
    {swatch}
    <div style={{ display: "flex", flexDirection: "column", minWidth: 0, flex: 1, lineHeight: 1.25 }}>
      <span style={{ fontSize: 12.5, fontWeight: 500, color: theme.color.textPrimary, overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>{title}</span>
      {subtitle && <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{subtitle}</span>}
    </div>
    {trailing}
  </Focusable>
);

export const Check: FC<{ on: boolean }> = ({ on }) => (
  <span style={{
    width: 18,
    height: 18,
    borderRadius: "50%",
    flexShrink: 0,
    display: "grid",
    placeItems: "center",
    fontSize: 11,
    fontWeight: 700,
    color: on ? theme.color.onAccent : "transparent",
    background: on ? theme.color.accent : "transparent",
    boxShadow: on ? "none" : `inset 0 0 0 1.5px ${theme.color.textMuted}`,
  }}>✓</span>
);

export const Swatch: FC<{ background: string; image?: string | null }> = ({ background, image }) => (
  <span style={{
    width: 44,
    height: 28,
    borderRadius: 5,
    flexShrink: 0,
    background: image ? `center / cover no-repeat url("${image}")` : background,
    boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
  }} />
);

export const Segmented: FC<{ options: { value: string; label: string }[]; value: string; onChange: (value: string) => void; centerLabels?: boolean }> = ({ options, value, onChange, centerLabels = false }) => (
  <Focusable flow-children="row" style={{ display: "grid", gridTemplateColumns: `repeat(${options.length}, 1fr)`, gap: 3, padding: 3, borderRadius: theme.radius.sm, background: "rgba(255,255,255,0.05)" }}>
    {options.map((option) => {
      const active = option.value === value;
      return (
        <Focusable
          key={option.value}
          onActivate={() => onChange(option.value)}
          onClick={() => onChange(option.value)}
          style={{
            ...(centerLabels ? { display: "flex", alignItems: "center", justifyContent: "center" } : {}),
            fontSize: theme.font.caption,
            textAlign: "center",
            padding: "7px 2px",
            borderRadius: 6,
            lineHeight: 1.2,
            cursor: "pointer",
            color: active ? theme.color.textPrimary : theme.color.textMuted,
            fontWeight: active ? 600 : 400,
            background: active ? "rgba(255,255,255,0.1)" : "transparent",
            boxShadow: active ? `inset 0 0 0 1px ${theme.color.hairline}` : "none",
          }}
        >
          {option.label}
        </Focusable>
      );
    })}
  </Focusable>
);

const SettingLabel: FC<{ label: string; value?: ReactNode }> = ({ label, value }) => (
  <div style={{ display: "flex", alignItems: "baseline", gap: 8, padding: "0 2px" }}>
    <span style={{ flex: 1, fontSize: theme.font.body, color: theme.color.textPrimary }}>{label}</span>
    {value !== undefined && <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted, fontVariantNumeric: "tabular-nums" }}>{value}</span>}
  </div>
);

/**
 * Keeps the B that closes a dropdown's menu from travelling on to Panel's page, where B means
 * "back to the dashboard".
 */
function useMenuCancelGuard() {
  const openedAt = useRef(0);
  return {
    onMenuOpened: () => {
      openedAt.current = Date.now();
    },
    onChangeDone: () => {
      openedAt.current = 0;
    },
    onCancel: (event: { stopPropagation?: () => void }) => {
      if (!openedAt.current || Date.now() - openedAt.current > MENU_GUARD_MS) return;
      openedAt.current = 0;
      event.stopPropagation?.();
    },
  };
}

const MENU_GUARD_MS = 60000;

/** A setting with several choices: name on top, Steam's picker underneath. */
export function ValueRow<T extends string>({ label, value, options, onChange }: {
  label: string;
  value: T;
  options: readonly { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  const guard = useMenuCancelGuard();
  return (
    <Focusable onCancel={guard.onCancel} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <SettingLabel label={label} />
      <Dropdown
        menuLabel={label}
        selectedOption={value}
        rgOptions={options.map((o) => ({ data: o.value, label: o.label }))}
        onMenuOpened={guard.onMenuOpened}
        onChange={(option) => {
          guard.onChangeDone();
          onChange(option.data as T);
        }}
      />
    </Focusable>
  );
}

/** Two or three short choices: name on top, all of them visible underneath. */
export function ChoiceRow<T extends string>({ label, value, options, onChange }: {
  label: string;
  value: T;
  options: readonly { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <SettingLabel label={label} />
      <Segmented value={value} options={options.map((o) => ({ value: o.value, label: o.label }))} onChange={(v) => onChange(v as T)} />
    </div>
  );
}

/** An on/off setting in the same voice as the other rows: name, optional hint, a small switch. */
export const ToggleRow: FC<{ label: string; description?: string; checked: boolean; onChange: (checked: boolean) => void }> = ({ label, description, checked, onChange }) => (
  <Focusable
    role="switch"
    aria-checked={checked}
    aria-label={label}
    onActivate={() => onChange(!checked)}
    onClick={() => onChange(!checked)}
    style={{ display: "flex", alignItems: "center", gap: 10, padding: "7px 6px", borderRadius: theme.radius.sm, cursor: "pointer" }}
  >
    <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
      <span style={{ fontSize: theme.font.body, color: theme.color.textPrimary }}>{label}</span>
      {description && <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted, lineHeight: 1.35 }}>{description}</span>}
    </div>
    <span aria-hidden style={{ flexShrink: 0, width: 36, height: 20, borderRadius: 10, padding: 2, boxSizing: "border-box", background: checked ? theme.color.accent : "rgba(255,255,255,0.18)", transition: "background 160ms ease" }}>
      <span style={{ display: "block", width: 16, height: 16, borderRadius: "50%", background: "#fff", transform: `translateX(${checked ? 16 : 0}px)`, transition: "transform 160ms ease" }} />
    </span>
  </Focusable>
);

/** A level: name and current value on top, a slider underneath. */
export const SliderRow: FC<{ label: string; value: number; min: number; max: number; step: number; format: (value: number) => string; onChange: (value: number) => void }> = ({ label, value, min, max, step, format, onChange }) => (
  <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
    <SettingLabel label={label} value={format(value)} />
    <ContainedSlider value={value} min={min} max={max} step={step} bottomSeparator="none" onChange={onChange} />
  </div>
);

const CORNERS: readonly OverlayCorner[] = ["top-left", "top-right", "bottom-left", "bottom-right"];

/** The four screen corners as a small screen: pick where the floating card lives. */
export function CornerPicker({ label, value, labels, onChange }: {
  label: string;
  value: OverlayCorner;
  labels: Record<OverlayCorner, string>;
  onChange: (value: OverlayCorner) => void;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <SettingLabel label={label} value={labels[value]} />
      <Focusable flow-children="grid" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, padding: 6, aspectRatio: "16 / 9", borderRadius: theme.radius.sm, background: "rgba(255,255,255,0.05)", boxShadow: `inset 0 0 0 1px ${theme.color.hairline}` }}>
        {CORNERS.map((corner) => {
          const on = corner === value;
          return (
            <Focusable
              key={corner}
              aria-label={labels[corner]}
              onActivate={() => onChange(corner)}
              onClick={() => onChange(corner)}
              style={{ display: "flex", alignItems: corner.startsWith("top") ? "flex-start" : "flex-end", justifyContent: corner.endsWith("left") ? "flex-start" : "flex-end", padding: 6, borderRadius: 6, cursor: "pointer", background: on ? `rgba(${theme.color.accentRgb},0.14)` : "transparent" }}
            >
              <span style={{ width: 34, height: 20, borderRadius: 5, background: on ? theme.color.accent : "rgba(255,255,255,0.18)" }} />
            </Focusable>
          );
        })}
      </Focusable>
    </div>
  );
}

/** Rarely touched settings stay folded; the choice is remembered per id. */
export const MoreSettings: FC<{ id: string; label: string; children: ReactNode }> = ({ id, label, children }) => {
  const [open, setOpen] = useState(() => !isCollapsed(id, true));
  const toggle = () => {
    setOpen(!open);
    setCollapsed(id, open);
  };
  const Chevron = open ? LuChevronDown : LuChevronRight;
  return (
    <>
      <Focusable
        onActivate={toggle}
        onClick={toggle}
        style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 6px", borderRadius: theme.radius.sm, cursor: "pointer", color: theme.color.textMuted, fontSize: theme.font.caption, fontWeight: 600 }}
      >
        <span style={{ flex: 1 }}>{label}</span>
        <Chevron size={14} />
      </Focusable>
      {open && <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>{children}</div>}
    </>
  );
};

export interface ItemAction {
  label: string;
  destructive?: boolean;
  onSelect: () => void;
}

export interface ItemMenu {
  title: string;
  /** Footer legend next to the Options button. */
  hint: string;
  actions: ItemAction[];
}

/** Steam's own context menu: Options (☰) on a controller, a long press or right click on touch. */
export function openItemMenu(menu: ItemMenu, anchor?: EventTarget | null): void {
  showContextMenu(
    <Menu label={menu.title}>
      {menu.actions.map((action) => (
        <MenuItem key={action.label} tone={action.destructive ? "destructive" : undefined} onSelected={action.onSelect}>{action.label}</MenuItem>
      ))}
    </Menu>,
    anchor ?? window,
  );
}

export function menuHandlers(menu: ItemMenu | undefined) {
  if (!menu || menu.actions.length === 0) return {};
  return {
    onOptionsButton: (event: Event) => openItemMenu(menu, event.currentTarget),
    onOptionsActionDescription: menu.hint,
    onContextMenu: (event: { preventDefault(): void; currentTarget: EventTarget }) => {
      event.preventDefault();
      openItemMenu(menu, event.currentTarget);
    },
  };
}

export const TILE_PX = 76;

/** Square pick in a horizontal strip: artwork or swatch, a label, a check when chosen. */
export const Tile: FC<{
  label: string;
  image?: string | null;
  background?: string;
  icon?: ReactNode;
  selected?: boolean;
  dashed?: boolean;
  /** Edit mode: a remove badge shows and activating the tile removes it. */
  removing?: boolean;
  /** Small mark in the corner telling what kind of item it is. */
  badge?: ReactNode;
  /** Part of a multiple choice: an empty ring shows when not chosen and the artwork dims. */
  selectable?: boolean;
  /** Footer legend for A. */
  activateHint?: string;
  menu?: ItemMenu;
  onActivate: () => void;
}> = ({ label, image, background, icon, selected, dashed, removing, badge, selectable, activateHint, menu, onActivate }) => (
  <Focusable
    onActivate={onActivate}
    onClick={onActivate}
    onOKActionDescription={activateHint}
    {...menuHandlers(menu)}
    style={{ "--pdc-focus-radius": "12px", width: TILE_PX, flexShrink: 0, display: "flex", flexDirection: "column", gap: 5, cursor: "pointer", borderRadius: 12, padding: 0, background: "transparent" } as CSSProperties}
  >
    <span style={{
      position: "relative",
      width: TILE_PX,
      height: TILE_PX,
      borderRadius: 12,
      display: "grid",
      placeItems: "center",
      color: theme.color.textMuted,
      background: image ? `center / cover no-repeat url("${image}"), ${background ?? "#15171c"}` : background ?? "transparent",
      boxShadow: selected
        ? `inset 0 0 0 2px ${theme.color.accent}`
        : dashed ? `inset 0 0 0 1.5px ${theme.color.hairline}` : `inset 0 0 0 1px ${theme.color.hairline}`,
      outline: dashed ? `1px dashed ${theme.color.textMuted}` : "none",
      outlineOffset: -6,
      opacity: selectable && !selected && !removing ? 0.55 : 1,
      transition: "opacity 160ms ease",
    }}>
      {icon}
      {badge && (
        <span style={{ position: "absolute", left: 5, bottom: 5, width: 20, height: 20, borderRadius: 6, display: "grid", placeItems: "center", background: "rgba(0,0,0,0.62)", color: "#fff" }}>
          {badge}
        </span>
      )}
      {removing && (
        <span style={{ position: "absolute", left: 5, top: 5, width: 20, height: 20, borderRadius: "50%", display: "grid", placeItems: "center", background: "rgba(220,60,60,0.95)", color: "#fff" }}>
          <LuX size={12} strokeWidth={3} />
        </span>
      )}
      {selectable && !selected && !removing && (
        <span style={{ position: "absolute", right: 5, top: 5, width: 18, height: 18, borderRadius: "50%", boxSizing: "border-box", border: "1.5px solid rgba(255,255,255,0.85)", background: "rgba(0,0,0,0.35)" }} />
      )}
      {selected && !removing && (
        <span style={{ position: "absolute", right: 5, top: 5, width: 18, height: 18, borderRadius: "50%", display: "grid", placeItems: "center", background: theme.color.accent, color: theme.color.onAccent }}>
          <LuCheck size={11} strokeWidth={3} />
        </span>
      )}
    </span>
    <span style={{ fontSize: 11, lineHeight: 1.2, color: selected ? theme.color.textPrimary : theme.color.textMuted, overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", textAlign: "center" }}>{label}</span>
  </Focusable>
);

export const TileStrip: FC<{ children: ReactNode }> = ({ children }) => (
  <Focusable flow-children="row" style={{ display: "flex", gap: 10, overflowX: "auto", padding: "2px 2px 4px", scrollbarWidth: "none" } as CSSProperties}>
    {children}
  </Focusable>
);
