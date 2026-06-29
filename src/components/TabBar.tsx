import { CSSProperties, FC, ReactNode } from "react";
import { Focusable } from "@decky/ui";
import { theme } from "../theme";

export interface TabItem {
  id: string;
  icon: ReactNode;
  label: string;
}

interface TabBarProps {
  tabs: TabItem[];
  activeId: string;
  onSelect: (id: string) => void;
}

/**
 * Segmented tab bar — the control-center navigator. Shares the "pattern A"
 * visual language with the profile selector and language flags (Focusable,
 * active = full opacity + accent fill). Presentation only: it renders whatever
 * the section registry provides, so swapping it for a dropdown later touches
 * nothing else.
 */
export const TabBar: FC<TabBarProps> = ({ tabs, activeId, onSelect }) => {
  const seg = (active: boolean): CSSProperties => ({
    flex: 1,
    textAlign: "center",
    padding: "6px 8px",
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
  });

  return (
    <Focusable
      style={{
        display: "flex",
        gap: 4,
        padding: 4,
        borderRadius: theme.radius.md,
        background: theme.color.surfaceRaised,
        boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
      }}
    >
      {tabs.map((tab) => (
        <Focusable
          key={tab.id}
          style={seg(tab.id === activeId)}
          onActivate={() => onSelect(tab.id)}
          onClick={() => onSelect(tab.id)}
        >
          <span style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 5 }}>
            {tab.icon} {tab.label}
          </span>
        </Focusable>
      ))}
    </Focusable>
  );
};
