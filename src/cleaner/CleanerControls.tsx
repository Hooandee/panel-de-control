import { Focusable } from "@decky/ui";
import type { CSSProperties, FC, ReactNode } from "react";
import { LuCircleAlert, LuCircleCheck, LuX } from "react-icons/lu";
import { theme } from "../theme";
import { useI18n } from "../i18n";

export const cleanerColumn: CSSProperties = { display: "flex", flexDirection: "column", gap: theme.space.sm, minWidth: 0 };
export const cleanerCaption: CSSProperties = { fontSize: theme.font.caption, color: theme.color.textMuted, lineHeight: 1.5 };

export const CleanerButton: FC<{
  label: string;
  children: ReactNode;
  onActivate: () => void;
  disabled?: boolean;
  checked?: boolean;
  selected?: boolean;
  primary?: boolean;
  danger?: boolean;
  style?: CSSProperties;
  role?: string;
}> = ({ label, children, onActivate, disabled, checked, selected, primary, danger, style, role }) => {
  const activate = () => { if (!disabled) onActivate(); };
  return <Focusable
    role={role ?? (checked === undefined ? "button" : "checkbox")}
    aria-label={label}
    aria-checked={checked}
    aria-selected={selected}
    aria-disabled={!!disabled}
    tabIndex={disabled ? -1 : 0}
    onActivate={activate}
    onClick={activate}
    onOKActionDescription={label}
    style={{ width: "100%", minWidth: 0, padding: 0, borderRadius: theme.radius.sm }}
  >
    <div style={{
      ...theme.card,
      width: "100%",
      boxSizing: "border-box",
      minHeight: 40,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      gap: 8,
      padding: "10px 12px",
      borderRadius: theme.radius.sm,
      fontSize: theme.font.body,
      color: primary ? theme.color.onAccent : danger ? theme.color.danger : theme.color.textPrimary,
      background: primary ? theme.color.accent : selected ? `${theme.color.accent}18` : theme.color.surfaceRaised,
      boxShadow: selected ? `inset 0 0 0 1px ${theme.color.accent}66` : theme.card.boxShadow,
      opacity: disabled ? 0.45 : 1,
      cursor: disabled ? "default" : "pointer",
      ...style,
    }}>{children}</div>
  </Focusable>;
};

export const CleanerNotice: FC<{ children: ReactNode; warning?: boolean }> = ({ children, warning }) => (
  <div style={{ ...cleanerCaption, display: "flex", alignItems: "flex-start", gap: 8, padding: "9px 10px", borderRadius: theme.radius.sm, background: warning ? `${theme.color.warn}10` : theme.color.surfaceRaised, color: warning ? theme.color.warn : theme.color.textMuted }}>
    <LuCircleAlert size={15} style={{ flexShrink: 0, marginTop: 1 }} />
    <span>{children}</span>
  </div>
);

export const CleanerResult: FC<{
  bytes: string;
  failed: boolean;
  counts: string;
  onClose: () => void;
}> = ({ bytes, failed, counts, onClose }) => {
  const { t } = useI18n();
  return <div style={{ ...theme.card, ...cleanerColumn, padding: 12 }}>
    <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: theme.font.body, fontWeight: 600 }}>
      {failed ? <LuCircleAlert size={17} color={theme.color.warn} /> : <LuCircleCheck size={17} color={theme.color.ok} />}
      <span style={{ flex: 1 }}>{t("cleaner.result.title")}</span>
      <div style={{ width: 30 }}>
        <CleanerButton label={t("cleaner.result.close")} onActivate={onClose} style={{ minHeight: 30, padding: 6, background: "transparent", boxShadow: "none" }}><LuX size={15} /></CleanerButton>
      </div>
    </div>
    <div style={{ fontSize: 22, fontWeight: 650, fontVariantNumeric: "tabular-nums" }}>{bytes}</div>
    <div style={cleanerCaption}>{counts}</div>
  </div>;
};
