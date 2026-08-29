import { ButtonItem, Navigation, PanelSectionRow } from "@decky/ui";
import { LuPaintbrush, LuRefreshCw } from "react-icons/lu";

import { ThemeCard } from "../components/ThemeCard";
import { openThemeDetailsModal } from "../components/ThemeDetailsModal";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { useThemes } from "../themes/useThemes";

export function TemasSection() {
  const { t } = useI18n();
  const controller = useThemes();
  const status = controller.snapshot.status;

  return (
    <PanelSectionRow>
      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.section, marginTop: theme.space.sm }}>
        <div style={{ ...theme.card, padding: theme.space.md }}>
          <div style={{ color: theme.color.textPrimary, fontSize: theme.font.body, fontWeight: 750, display: "flex", alignItems: "center", gap: 7 }}>
            <LuPaintbrush size={17} color={theme.color.accent} />
            {t("themes.title")}
          </div>
          <div style={{ color: theme.color.textMuted, fontSize: theme.font.caption, lineHeight: 1.45, marginTop: theme.space.xs }}>
            {t("themes.engine")}
          </div>
        </div>

        {controller.loading ? (
          <div style={{ ...theme.card, padding: theme.space.md, color: theme.color.textMuted, fontSize: theme.font.body }}>
            {t("themes.loading")}
          </div>
        ) : status !== "ready" ? (
          <div style={{ ...theme.card, padding: theme.space.md }}>
            <div style={{ color: status === "error" ? theme.color.warn : theme.color.textPrimary, fontSize: theme.font.body, fontWeight: 700 }}>
              {t(`themes.cssLoader.${status}`)}
            </div>
            {status === "incompatible" && (
              <div style={{ color: theme.color.textMuted, fontSize: theme.font.caption, marginTop: theme.space.xs }}>
                {t("themes.cssLoader.version", {
                  detected: controller.snapshot.backendVersion ?? "—",
                  required: controller.snapshot.requiredBackendVersion ?? "—",
                })}
              </div>
            )}
            {controller.error && (
              <div style={{ color: theme.color.warn, fontSize: theme.font.caption, marginTop: theme.space.xs }}>
                {controller.error}
              </div>
            )}
            <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm, marginTop: theme.space.md }}>
              {status === "missing" && (
                <ButtonItem layout="below" onClick={() => Navigation.Navigate("/decky/store")}>
                  {t("themes.cssLoader.openStore")}
                </ButtonItem>
              )}
              <ButtonItem layout="below" onClick={() => void controller.refresh()}>
                <LuRefreshCw size={14} /> {t("themes.retry")}
              </ButtonItem>
            </div>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
            {controller.cards.map((card) => (
              <ThemeCard
                key={card.id}
                card={card}
                operation={controller.operation}
                onOpen={() => openThemeDetailsModal(card.id, () => void controller.refresh())}
              />
            ))}
          </div>
        )}
      </div>
    </PanelSectionRow>
  );
}
