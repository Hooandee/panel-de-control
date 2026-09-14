import { Focusable, NavEntryPositionPreferences } from "@decky/ui";
import { type CSSProperties, type ReactNode, useEffect, useRef } from "react";
import { useI18n } from "../i18n";
import type { SectionDef } from "../sections/types";
import { theme } from "../theme";

export interface DashboardProps {
  sections: SectionDef[];
  activeId: string | null;
  settingsBadge?: ReactNode;
  onOpenSection: (id: string) => void;
}

const gridStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
  gap: theme.space.sm,
};

const cardStyle: CSSProperties = {
  minWidth: 0,
  minHeight: 104,
  padding: `${theme.space.sm}px 6px ${theme.space.md}px`,
  borderRadius: theme.radius.md,
  background: "transparent",
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "flex-start",
  gap: theme.space.xs,
  textAlign: "center",
  cursor: "pointer",
  boxSizing: "border-box",
  position: "relative",
  width: "100%",
};

function useIdempotentAction() {
  const locked = useRef(new Set<string>());

  return (key: string, action: () => void) => () => {
    if (locked.current.has(key)) return;
    locked.current.add(key);
    try {
      action();
    } finally {
      queueMicrotask(() => locked.current.delete(key));
    }
  };
}

export function Dashboard({ sections, activeId, settingsBadge, onOpenSection }: DashboardProps) {
  const { t } = useI18n();
  const activeCard = useRef<HTMLDivElement>(null);
  const idempotentAction = useIdempotentAction();

  useEffect(() => {
    activeCard.current?.scrollIntoView({ block: "nearest" });
  }, [activeId]);

  return (
    <div>
      <Focusable
        data-testid="dashboard-grid"
        navEntryPreferPosition={NavEntryPositionPreferences.PREFERRED_CHILD}
        style={gridStyle}
      >
        {sections.map((section) => {
          const label = section.label || t(section.labelKey);
          const description = t(section.descriptionKey);
          const openSection = idempotentAction(`section:${section.id}`, () => onOpenSection(section.id));

          return (
            <Focusable
              key={section.id}
              ref={section.id === activeId ? activeCard : undefined}
              className="pdc-dashboard-card"
              focusClassName="pdc-dashboard-card-focused"
              role="button"
              data-testid="dashboard-card"
              data-section-id={section.id}
              data-pdc-focus-radius
              preferredFocus={section.id === activeId}
              aria-label={`${label}. ${description}`}
              onActivate={openSection}
              onClick={openSection}
              onFocus={(event) => event.currentTarget.scrollIntoView({ block: "nearest" })}
              style={{
                minWidth: 0,
                "--pdc-card-accent": section.accent,
              } as CSSProperties}
            >
              <div className="pdc-dashboard-card-surface" style={cardStyle}>
                <span
                  className="pdc-dashboard-card-icon"
                  aria-hidden="true"
                  style={{
                    width: 42,
                    height: 42,
                    borderRadius: 11,
                    background: section.accent,
                    color: "white",
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                    position: "relative",
                  }}
                >
                  {section.icon(24)}
                  {section.id === "settings" && settingsBadge ? (
                    <span
                      style={{
                        position: "absolute",
                        top: -2,
                        right: -2,
                        display: "flex",
                      }}
                    >
                      {settingsBadge}
                    </span>
                  ) : null}
                </span>
                <span
                  className="pdc-dashboard-card-label"
                  style={{ color: theme.color.textPrimary, fontSize: theme.font.body, fontWeight: 700 }}
                >
                  {label}
                </span>
                <span
                  className="pdc-dashboard-card-description"
                  style={{
                    color: theme.color.textMuted,
                    fontSize: theme.font.caption,
                    lineHeight: 1.35,
                    maxHeight: 30,
                    display: "-webkit-box",
                    WebkitBoxOrient: "vertical",
                    WebkitLineClamp: 2,
                    overflow: "hidden",
                  }}
                >
                  {description}
                </span>
              </div>
            </Focusable>
          );
        })}
      </Focusable>
    </div>
  );
}
