import { Focusable } from "@decky/ui";

import { theme } from "../theme";

export function SegmentedTabs<T extends string>({ label, tabs, value, onChange }: {
  label: string;
  tabs: readonly { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <Focusable
      role="tablist"
      aria-label={label}
      flow-children="horizontal"
      style={{
        display: "grid",
        gridTemplateColumns: `repeat(${tabs.length}, 1fr)`,
        gap: 3,
        padding: 3,
        borderRadius: theme.radius.sm,
        background: "rgba(255,255,255,0.05)",
      }}
    >
      {tabs.map((tab) => {
        const active = tab.value === value;
        return (
          <Focusable
            key={tab.value}
            role="tab"
            aria-selected={active}
            onActivate={() => onChange(tab.value)}
            onClick={() => onChange(tab.value)}
            style={{
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
            {tab.label}
          </Focusable>
        );
      })}
    </Focusable>
  );
}
