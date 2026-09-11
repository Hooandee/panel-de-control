import { type ReactNode } from "react";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { CompactBackAction } from "./CompactBackAction";
import { QamAction } from "./QamAction";

export interface TabsModeItem {
  id: string;
  label: string;
  accent: string;
  icon: ReactNode;
  badge?: ReactNode;
}

export interface TabsModeHeaderProps {
  items: TabsModeItem[];
  activeId: string;
  showBack: boolean;
  onBack: () => void;
  onSelect: (id: string) => void;
  trailing?: ReactNode;
}

function ShoulderKey({ children }: { children: ReactNode }) {
  return (
    <span
      aria-hidden="true"
      style={{
        minWidth: 16,
        height: 14,
        padding: "0 2px",
        borderRadius: 4,
        boxSizing: "border-box",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        color: theme.color.textMuted,
        background: theme.color.surfaceRaised,
        boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
        fontSize: 7.5,
        fontWeight: 800,
        letterSpacing: 0.2,
      }}
    >
      {children}
    </span>
  );
}

function SectionIcon({ item }: { item: TabsModeItem }) {
  return (
    <span
      aria-hidden="true"
      style={{
        width: 28,
        height: 28,
        borderRadius: 8,
        background: item.accent,
        color: "white",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0,
        position: "relative",
      }}
    >
      {item.icon}
      {item.badge ? (
        <span style={{ position: "absolute", top: -2, right: -2 }}>{item.badge}</span>
      ) : null}
    </span>
  );
}

function SideSection({
  item,
  side,
  onSelect,
}: {
  item: TabsModeItem;
  side: "left" | "right";
  onSelect: (id: string) => void;
}) {
  return (
    <div data-section-id={item.id} style={{ minWidth: 0 }}>
      <QamAction
        label={item.label}
        onPress={() => onSelect(item.id)}
        style={{
          minWidth: 0,
          width: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: side === "left" ? "flex-start" : "flex-end",
          gap: 2,
          cursor: "pointer",
        }}
      >
        {side === "left" ? <ShoulderKey>L1</ShoulderKey> : null}
        <span
          style={{
            minWidth: 0,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            color: theme.color.textMuted,
            fontSize: 9,
            fontWeight: 600,
            textAlign: side,
          }}
        >
          {item.label}
        </span>
        {item.badge}
        {side === "right" ? <ShoulderKey>R1</ShoulderKey> : null}
      </QamAction>
    </div>
  );
}

export function TabsModeHeader({
  items,
  activeId,
  showBack,
  onBack,
  onSelect,
  trailing,
}: TabsModeHeaderProps) {
  const { t } = useI18n();
  const activeIndex = Math.max(0, items.findIndex((item) => item.id === activeId));
  const active = items[activeIndex];
  const showShoulders = items.length > 1;
  const previous = showShoulders ? items[(activeIndex - 1 + items.length) % items.length] : undefined;
  const next = showShoulders ? items[(activeIndex + 1) % items.length] : undefined;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
      {showBack ? (
        <div
          data-testid="tabs-back-row"
          style={{
            minHeight: 28,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: theme.space.sm,
          }}
        >
          <CompactBackAction onBack={onBack} />
          {trailing ? (
            <div style={{ minWidth: 0, flex: "1 1 auto", display: "flex", justifyContent: "flex-end" }}>
              {trailing}
            </div>
          ) : null}
        </div>
      ) : trailing ? (
        <div
          data-testid="tabs-device-row"
          style={{ minWidth: 0, display: "flex", justifyContent: "flex-end" }}
        >
          {trailing}
        </div>
      ) : null}

      {active ? (
        <div
          data-testid="tabs-carousel"
          role="group"
          aria-label={t("home.changeSection")}
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(0, 1fr) minmax(96px, 1.1fr) minmax(0, 1fr)",
            alignItems: "center",
            gap: theme.space.xs,
            minHeight: 42,
          }}
        >
          {previous ? <SideSection item={previous} side="left" onSelect={onSelect} /> : <span />}
          <div
            data-section-id={active.id}
            aria-current="page"
            aria-label={active.label}
            style={{
              minWidth: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 6,
              color: theme.color.textPrimary,
            }}
          >
            <SectionIcon item={active} />
            <span
              style={{
                minWidth: 0,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                fontSize: theme.font.body,
                fontWeight: 750,
              }}
            >
              {active.label}
            </span>
          </div>
          {next ? <SideSection item={next} side="right" onSelect={onSelect} /> : <span />}
        </div>
      ) : null}
    </div>
  );
}
