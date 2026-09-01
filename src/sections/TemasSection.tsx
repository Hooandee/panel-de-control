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
  const publication = controller.publication;
  const catalogLoading = publication.status === "unchecked" || publication.status === "checking";
  const catalogUnavailable = publication.status === "disabled"
    || publication.status === "temporarily-unavailable"
    || publication.status === "recoverable-failure";
  const validEmptyCatalog = publication.status === "published" && controller.cards.length === 0;
  const cssChecking = controller.loading || controller.refreshing || controller.operation?.kind === "recovering";

  return (
    <PanelSectionRow>
      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.section, marginTop: theme.space.sm }}>
        <div style={{ ...theme.card, padding: theme.space.md }}>
          <div style={{ color: theme.color.textPrimary, fontSize: theme.font.body, fontWeight: 750, display: "flex", alignItems: "center", gap: 7 }}>
            <LuPaintbrush size={17} color={theme.color.accent} aria-hidden /> {t("themes.title")}
          </div>
          <div style={{ color: theme.color.textMuted, fontSize: theme.font.caption, lineHeight: 1.45, marginTop: theme.space.xs }}>{t("themes.engine")}</div>
        </div>

        {controller.loading ? (
          <div role="status" aria-live="polite" style={{ ...theme.card, padding: theme.space.md, color: theme.color.textMuted }}>{t("themes.loading")}</div>
        ) : controller.snapshot.status !== "ready" ? (
          <div style={{ ...theme.card, padding: theme.space.md }}>
            <div role="status" aria-live="polite" style={{ color: controller.snapshot.status === "error" ? theme.color.warn : theme.color.textPrimary, fontWeight: 700 }}>
              {t(`themes.cssLoader.${controller.snapshot.status}`)}
            </div>
            {controller.snapshot.status === "incompatible" ? (
              <div style={{ color: theme.color.textMuted, fontSize: theme.font.caption, marginTop: theme.space.xs }}>
                {t("themes.cssLoader.version", {
                  detected: controller.snapshot.backendVersion ?? "—",
                  required: controller.snapshot.requiredBackendVersion ?? "—",
                })}
              </div>
            ) : null}
            <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm, marginTop: theme.space.md }}>
              {controller.snapshot.status === "missing" ? (
                <ButtonItem layout="below" onClick={() => Navigation.Navigate("/decky/store")}>{t("themes.cssLoader.openStore")}</ButtonItem>
              ) : null}
              <ButtonItem layout="below" disabled={cssChecking} onClick={() => void controller.refresh()}>
                <LuRefreshCw size={14} aria-hidden /> {t(cssChecking ? "themes.loading" : "themes.retry")}
              </ButtonItem>
            </div>
          </div>
        ) : null}

        {publication.status === "cached" ? (
          <div style={{ ...theme.card, padding: theme.space.md, color: theme.color.warn }}>
            <div role="status">{t("themes.remote.cached")}</div>
            <div style={{ marginTop: theme.space.sm }}>
              <ButtonItem layout="below" disabled={controller.operation !== null} onClick={() => void controller.refreshPublication()}>{t("themes.remote.retry")}</ButtonItem>
            </div>
          </div>
        ) : null}

        {catalogLoading && controller.cards.length === 0 ? (
          <div role="status" aria-live="polite" style={{ ...theme.card, padding: theme.space.md, color: theme.color.textMuted }}>{t("themes.remote.checking")}</div>
        ) : null}
        {catalogUnavailable && controller.cards.length === 0 ? (
          <div style={{ ...theme.card, padding: theme.space.md }}>
            <div style={{ color: theme.color.warn }}>{t("themes.catalog.unavailable")}</div>
            <div style={{ marginTop: theme.space.sm }}>
              <ButtonItem layout="below" disabled={publication.status !== "disabled" && !publication.retryable} onClick={() => void controller.refreshPublication()}>
                <LuRefreshCw size={14} aria-hidden /> {t("themes.remote.retry")}
              </ButtonItem>
            </div>
          </div>
        ) : null}
        {validEmptyCatalog ? (
          <div style={{ ...theme.card, padding: theme.space.md, color: theme.color.textMuted }}>{t("themes.catalog.empty")}</div>
        ) : null}

        {controller.error ? (
          <div role="alert" style={{ ...theme.card, padding: theme.space.md, color: theme.color.warn }}>
            {t(controller.recoveryBlocked ? "themes.recovery.blocked" : "themes.operation.failed")}
          </div>
        ) : null}

        {controller.cards.length > 0 ? (
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
        ) : null}
      </div>
    </PanelSectionRow>
  );
}
