import { FC } from "react";
import { Focusable, PanelSectionRow } from "@decky/ui";
import { LuSparkles } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";

interface Props {
  /** True once any color change is active (offers "back to native"). */
  active: boolean;
  onApply: () => void;
  onReset: () => void;
}

/**
 * The one-tap "OLED look" hero — a visually distinct feature card (accent-tinted,
 * not a plain pill) so it reads as the headline action, not another toggle. HONEST
 * copy: it nudges the panel's COLOR toward an OLED (more vibrant + more contrast) —
 * it does not give an LCD real OLED blacks. Rendered only on LCD panels with support.
 */
export const OledLookCard: FC<Props> = ({ active, onApply, onReset }) => {
  const { t } = useI18n();
  return (
    <PanelSectionRow>
      <div
        style={{
          borderRadius: theme.radius.md,
          padding: theme.space.md,
          marginBottom: theme.space.card,
          overflow: "hidden",
          // Accent-tinted gradient so the hero card stands apart from the plain cards.
          background: `linear-gradient(135deg, rgba(78,161,255,0.18), rgba(78,161,255,0.04))`,
          boxShadow: `inset 0 0 0 1px rgba(78,161,255,0.35)`,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: theme.space.sm }}>
          <LuSparkles size={20} color={theme.color.accent} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: theme.font.body, fontWeight: 700, color: theme.color.textPrimary }}>
              {t("display.oled.title")}
            </div>
            <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
              {t("display.oled.desc")}
            </div>
          </div>
        </div>
        <Focusable style={{ display: "flex", gap: 6, marginTop: 10 }}>
          <Focusable
            style={{
              flex: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
              padding: "9px 10px", borderRadius: theme.radius.sm,
              background: theme.color.accent, color: "#ffffff", fontWeight: 700,
              fontSize: theme.font.body, cursor: "pointer",
            }}
            onActivate={onApply}
            onClick={onApply}
          >
            <LuSparkles size={15} />
            {t("display.oled.apply")}
          </Focusable>
          {active && (
            <Focusable
              style={{
                display: "flex", alignItems: "center", justifyContent: "center",
                padding: "9px 14px", borderRadius: theme.radius.sm,
                background: "rgba(255,255,255,0.06)", color: theme.color.textPrimary,
                fontSize: theme.font.body, cursor: "pointer",
              }}
              onActivate={onReset}
              onClick={onReset}
            >
              {t("display.native")}
            </Focusable>
          )}
        </Focusable>
      </div>
    </PanelSectionRow>
  );
};
