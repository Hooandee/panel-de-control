import type { FC } from "react";
import { PanelSectionRow, showModal } from "@decky/ui";
import { LuChevronRight, LuMonitorCog } from "react-icons/lu";

import { useI18n } from "../i18n";
import { useSteamPerformanceSurface } from "../steam/useSteamPerformanceSurface";
import { theme } from "../theme";
import { QamAction } from "./QamAction";
import { SteamPerformanceModal } from "./SteamPerformanceModal";

export const SteamPerformanceCard: FC = () => {
  const { t } = useI18n();
  const surface = useSteamPerformanceSurface();
  const available = surface.status === "ready";

  return (
    <PanelSectionRow>
      <div style={{ width: "100%" }}>
        <QamAction
          label={t("steam.performance.open")}
          onPress={() => {
            showModal(<SteamPerformanceModal />, window);
          }}
          style={{ display: "block", width: "100%", cursor: "pointer" }}
        >
          <div style={{
            ...theme.card,
            display: "flex",
            alignItems: "center",
            gap: theme.space.md,
            padding: theme.space.md,
            marginBottom: theme.space.card,
          }}>
            <span aria-hidden style={{
              width: 38,
              height: 38,
              flexShrink: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              borderRadius: theme.radius.sm,
              color: theme.color.accent,
              background: `rgba(${theme.color.accentRgb},0.12)`,
              boxShadow: `inset 0 0 0 1px rgba(${theme.color.accentRgb},0.2)`,
            }}>
              <LuMonitorCog size={19} />
            </span>

            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{
                color: theme.color.textPrimary,
                fontSize: theme.font.body,
                fontWeight: 700,
                lineHeight: 1.25,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}>
                {t("steam.performance.title")}
              </div>
              <div style={{
                marginTop: 3,
                color: theme.color.textMuted,
                fontSize: theme.font.caption,
                lineHeight: 1.35,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}>
                {t("steam.performance.cardSummary")}
              </div>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, flexShrink: 0 }}>
              <span
                role="status"
                aria-label={available ? t("steam.performance.synced") : t("steam.performance.unavailable")}
                style={{
                  width: 7,
                  height: 7,
                  borderRadius: 999,
                  background: available ? theme.color.ok : theme.color.textMuted,
                  boxShadow: available ? `0 0 8px rgba(126,224,160,0.38)` : undefined,
                }}
              />
              <LuChevronRight size={17} color={theme.color.textMuted} aria-hidden />
            </div>
          </div>
        </QamAction>
      </div>
    </PanelSectionRow>
  );
};
