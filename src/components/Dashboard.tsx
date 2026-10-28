import { Focusable, NavEntryPositionPreferences } from "@decky/ui";
import { type CSSProperties, type ReactNode, useEffect, useRef } from "react";
import { useI18n } from "../i18n";
import type { SectionDef } from "../sections/types";
import { SectionGlyph, sectionGlyphStyles } from "./SectionGlyph";
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
  gap: "var(--pdc-dashboard-gap, 8px)",
};

const cardStyle: CSSProperties = {
  minWidth: 0,
  minHeight: "var(--pdc-dashboard-height, 104px)",
  padding: "var(--pdc-dashboard-padding, 8px 6px 12px)",
  borderRadius: "inherit",
  background: "transparent",
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "flex-start",
  gap: "var(--pdc-dashboard-inner-gap, 4px)",
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
  const grid = useRef<HTMLDivElement>(null);
  const activeCard = useRef<HTMLDivElement>(null);
  const idempotentAction = useIdempotentAction();

  useEffect(() => {
    activeCard.current?.scrollIntoView({ block: "nearest" });
  }, [activeId]);

  return (
    <div>
      <style>{sectionGlyphStyles}</style>
      <Focusable
        ref={grid}
        data-testid="dashboard-grid"
        navEntryPreferPosition={NavEntryPositionPreferences.PREFERRED_CHILD}
        style={gridStyle}
      >
        {sections.map((section, index) => {
          const label = section.label || t(section.labelKey);
          const description = t(section.descriptionKey);
          const openSection = idempotentAction(`section:${section.id}`, () => { grid.current?.ownerDocument.dispatchEvent(new CustomEvent("pdc-section-feedback", { detail: { id: section.id, kind: "open" } })); onOpenSection(section.id); });

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
              preferredFocus={activeId ? section.id === activeId : index === 0}
              aria-label={`${label}. ${description}`}
              onActivate={openSection}
              onClick={openSection}
              onFocus={(event) => { event.currentTarget.scrollIntoView({ block: "nearest" }); event.currentTarget.ownerDocument.dispatchEvent(new CustomEvent("pdc-section-feedback", { detail: { id: section.id, kind: "move" } })); }}
              style={{
                minWidth: 0,
                display: "flex",
                alignItems: "stretch",
                "--pdc-card-accent": section.accent,
              } as CSSProperties}
            >
              <div className="pdc-dashboard-card-surface" style={cardStyle}>
                <span
                  className="pdc-dashboard-card-icon"
                  aria-hidden="true"
                  style={{
                    width: "var(--pdc-dashboard-icon, 42px)",
                    height: "var(--pdc-dashboard-icon, 42px)",
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
                  <SectionGlyph id={section.id} fallback={section.icon(24)} />
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
                  style={{ color: theme.color.textPrimary, fontSize: "var(--pdc-dashboard-label, 13px)", fontWeight: 700 }}
                >
                  {label}
                </span>
                <span
                  className="pdc-dashboard-card-description"
                  style={{
                    color: theme.color.textMuted,
                    fontSize: "var(--pdc-dashboard-caption, 11px)",
                    lineHeight: 1.35,
                    maxHeight: "var(--pdc-dashboard-description-height, 30px)",
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
