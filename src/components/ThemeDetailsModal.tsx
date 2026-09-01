import { ButtonItem, Focusable, ModalRoot, Navigation, showModal } from "@decky/ui";
import { type CSSProperties, useState } from "react";
import { LuPower, LuRefreshCw, LuSparkles } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { groupThemePatches } from "../themes/patchGroups";
import { localizePublishedText } from "../themes/remotePublication";
import { useThemes } from "../themes/useThemes";
import { FocusRoot } from "./FocusRoot";
import { ThemePatchControl } from "./ThemePatchControl";

interface ThemeDetailsModalProps {
  themeId: string;
  closeModal?: () => void;
}

const THEME_CONTROL_RESET = `
[data-pdc-theme-settings] { color: ${theme.color.textPrimary} !important; }
[data-pdc-theme-settings] [data-pdc-theme-muted] { color: ${theme.color.textMuted} !important; }
[data-pdc-theme-settings] [data-pdc-theme-warning] { color: ${theme.color.warn} !important; }
[data-pdc-theme-settings] [data-pdc-theme-patch-control],
[data-pdc-theme-settings] [data-pdc-theme-status-surface] {
  background: ${theme.color.surfaceRaised} !important;
  box-shadow: inset 0 0 0 1px ${theme.color.hairline} !important;
  color: ${theme.color.textPrimary} !important;
}
[data-pdc-theme-settings] [data-pdc-theme-patch-control] > .Panel,
[data-pdc-theme-settings] [data-pdc-theme-patch-control] > div,
[data-pdc-theme-settings] [data-pdc-theme-action] > div {
  background: transparent !important;
  background-image: none !important;
  border: 0 !important;
  box-shadow: none !important;
  color: inherit !important;
}
[data-pdc-theme-settings] [data-pdc-theme-slider] :is(.gpfocus,.gpfocuswithin) {
  background: transparent !important;
  outline-color: ${theme.color.accent} !important;
}
`;

const STATUS_SURFACE: CSSProperties = {
  borderRadius: theme.radius.md,
  minWidth: 0,
  padding: theme.space.md,
  marginBottom: theme.space.section,
};

function formatVersion(value: string): string {
  return value.toLowerCase().startsWith("v") ? value : `v${value}`;
}

export function ThemeDetailsModal({ themeId, closeModal }: ThemeDetailsModalProps) {
  const { lang, t } = useI18n();
  const controller = useThemes();
  const [confirmation, setConfirmation] = useState<{ kind: "install" | "update"; version: string } | null>(null);
  const card = controller.cards.find((candidate) => candidate.id === themeId);
  const cancelOrClose = confirmation ? () => setConfirmation(null) : closeModal;

  if (controller.loading && !card) {
    return (
      <ModalRoot bAllowFullSize onCancel={closeModal} onEscKeypress={closeModal}>
        <FocusRoot><div role="status" aria-live="polite" style={{ padding: theme.space.lg }}>{t("themes.loading")}</div></FocusRoot>
      </ModalRoot>
    );
  }
  if (!card) {
    return (
      <ModalRoot bAllowFullSize onCancel={closeModal} onEscKeypress={closeModal}>
        <FocusRoot><div style={{ padding: theme.space.lg, color: theme.color.warn }}>{t("themes.details.unavailable")}</div></FocusRoot>
      </ModalRoot>
    );
  }

  const cssReady = controller.snapshot.status === "ready";
  const operationBusy = controller.operation !== null;
  const actionsBlocked = operationBusy || controller.recoveryBlocked || !cssReady;
  const activationBlocked = actionsBlocked
    || (!card.active && card.release.compatibility !== "compatible");
  const installing = controller.operation?.kind === "installing" && controller.operation.themeId === card.id;
  const activating = controller.operation?.kind === "activating" && controller.operation.themeId === card.id;
  const deactivating = controller.operation?.kind === "deactivating" && controller.operation.themeId === card.id;
  const displayName = localizePublishedText(card.release.displayName, lang);
  const description = localizePublishedText(card.release.description, lang);
  const releaseNote = localizePublishedText(card.release.notes, lang);
  const groups = groupThemePatches(card.cssLoaderTheme?.patches ?? []);

  return (
    <ModalRoot bAllowFullSize onCancel={cancelOrClose} onEscKeypress={cancelOrClose}>
      <FocusRoot style={{ minHeight: "100%" }}>
        <Focusable style={{ minHeight: "100%" }}>
          <div data-testid="theme-settings-content" data-pdc-theme-settings="true" style={{ maxWidth: 760, margin: "0 auto", padding: "8px 8px 54px", color: theme.color.textPrimary }}>
            <style>{THEME_CONTROL_RESET}</style>
            <header style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(150px, 220px)", alignItems: "center", gap: theme.space.lg, marginBottom: 22 }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ color: theme.color.accent, fontSize: theme.font.caption, fontWeight: 800, letterSpacing: 1.2, textTransform: "uppercase" }}>{t("themes.details.eyebrow")}</div>
                <h2 style={{ fontSize: 34, lineHeight: 1, margin: "8px 0 10px", letterSpacing: -1 }}>{displayName}</h2>
                <div data-pdc-theme-muted style={{ lineHeight: 1.45 }}>{description}</div>
                <div data-pdc-theme-muted style={{ display: "flex", flexWrap: "wrap", gap: 7, marginTop: 9, fontSize: theme.font.caption }}>
                  <span>{card.release.author}</span>
                  {card.installedVersion ? <span>{t("themes.version.installed", { version: formatVersion(card.installedVersion) })}</span> : null}
                  <span>{t("themes.version.published", { version: formatVersion(card.release.publishedVersion) })}</span>
                  {card.release.tags.map((tag) => <span key={tag}>#{tag}</span>)}
                </div>
              </div>
              {card.installed ? (
                <div data-pdc-theme-action="true">
                  <ButtonItem
                    layout="below"
                    disabled={activationBlocked}
                    onClick={() => void (card.active ? controller.deactivate(card.id) : controller.activate(card.id))}
                  >
                    {card.active ? <LuPower size={14} aria-hidden /> : <LuSparkles size={14} aria-hidden />}{" "}
                    {t(card.active
                      ? deactivating ? "themes.action.deactivating" : "themes.action.deactivate"
                      : activating ? "themes.action.activating" : "themes.action.activate")}
                  </ButtonItem>
                </div>
              ) : null}
            </header>

            {!cssReady ? (
              <div data-pdc-theme-status-surface="true" style={STATUS_SURFACE}>
                <div role="status" aria-live="polite">{t(`themes.cssLoader.${controller.snapshot.status}`)}</div>
                {controller.snapshot.status === "incompatible" ? (
                  <div data-pdc-theme-muted style={{ marginTop: theme.space.xs }}>
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
                  <ButtonItem layout="below" disabled={controller.refreshing} onClick={() => void controller.refresh()}>
                    <LuRefreshCw size={14} aria-hidden /> {t(controller.refreshing ? "themes.loading" : "themes.retry")}
                  </ButtonItem>
                </div>
              </div>
            ) : null}

            {controller.publication.status === "cached" ? (
              <div data-pdc-theme-status-surface="true" style={STATUS_SURFACE}>
                <div role="status" data-pdc-theme-warning>{t("themes.remote.cached")}</div>
                <div style={{ marginTop: theme.space.sm }}>
                  <ButtonItem layout="below" disabled={operationBusy} onClick={() => void controller.refreshPublication()}>{t("themes.remote.retry")}</ButtonItem>
                </div>
              </div>
            ) : null}

            {controller.error ? (
              <div data-pdc-theme-status-surface="true" role="alert" style={STATUS_SURFACE}>
                <div data-pdc-theme-warning>{t(controller.recoveryBlocked ? "themes.recovery.blocked" : "themes.operation.failed")}</div>
              </div>
            ) : null}

            {card.release.compatibility !== "compatible" ? (
              <div data-pdc-theme-status-surface="true" style={STATUS_SURFACE}>
                <div data-pdc-theme-warning>{t(`themes.remote.${card.release.compatibility}`)}</div>
              </div>
            ) : null}

            {releaseNote ? (
              <div data-pdc-theme-status-surface="true" style={STATUS_SURFACE}>
                <div style={{ fontWeight: 750 }}>{t("themes.remote.notes")}</div>
                <div data-pdc-theme-muted style={{ marginTop: theme.space.xs, lineHeight: 1.45 }}>{releaseNote}</div>
              </div>
            ) : null}

            {confirmation ? (
              <div data-pdc-theme-status-surface="true" role="group" aria-labelledby="theme-install-confirmation-title" style={STATUS_SURFACE}>
                <div id="theme-install-confirmation-title" style={{ fontWeight: 750 }}>{t(confirmation.kind === "update" ? "themes.update.confirm.title" : "themes.install.confirm.title")}</div>
                <div data-pdc-theme-muted style={{ marginTop: theme.space.xs }}>{t(confirmation.kind === "update" ? "themes.update.confirm.desc" : "themes.install.confirm.desc", { name: displayName })}</div>
                <div style={{ display: "flex", gap: theme.space.sm, marginTop: theme.space.md }}>
                  <ButtonItem layout="below" disabled={actionsBlocked} onClick={() => {
                    const exactVersion = confirmation.version;
                    setConfirmation(null);
                    void controller.install(card.id, { version: exactVersion });
                  }}>{t(confirmation.kind === "update" ? "themes.update.confirm.ok" : "themes.install.confirm.ok")}</ButtonItem>
                  <ButtonItem layout="below" disabled={operationBusy} onClick={() => setConfirmation(null)}>{t("themes.install.confirm.cancel")}</ButtonItem>
                </div>
              </div>
            ) : null}

            {cssReady && card.installable && card.targetVersion && (!card.installed || card.updateAvailable) ? (
              <div data-pdc-theme-status-surface="true" style={STATUS_SURFACE}>
                <div style={{ fontWeight: 750 }}>{t(card.installed ? "themes.update.ready" : "themes.install.ready")}</div>
                <div style={{ marginTop: theme.space.md }}>
                  <ButtonItem layout="below" disabled={actionsBlocked} onClick={() => setConfirmation({
                    kind: card.installed ? "update" : "install",
                    version: card.targetVersion!,
                  })}>{t(installing ? card.installed ? "themes.action.updating" : "themes.action.installing" : card.installed ? "themes.action.update" : "themes.action.install")}</ButtonItem>
                </div>
              </div>
            ) : null}

            {card.installed && groups.length === 0 ? (
              <div data-pdc-theme-status-surface="true" style={STATUS_SURFACE}><span data-pdc-theme-muted>{t("themes.patches.empty")}</span></div>
            ) : null}
            {card.installed && groups.length > 0 ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
                {groups.map((group) => {
                  const headingId = `theme-patch-group-${group.id}`;
                  return (
                    <section key={group.id} aria-labelledby={headingId} style={{ minWidth: 0 }}>
                      <h3 id={headingId} data-pdc-theme-muted style={{ ...theme.sectionLabel, margin: `0 0 ${theme.space.sm}px` }}>{t(`themes.group.${group.id}`)}</h3>
                      <div role="list" style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
                        {group.patches.map((patch) => (
                          <div key={patch.name} role="listitem">
                            <ThemePatchControl patch={patch} disabled={actionsBlocked} onChange={(value) => void controller.setPatch(card.id, patch.name, value)} />
                          </div>
                        ))}
                      </div>
                    </section>
                  );
                })}
              </div>
            ) : null}
          </div>
        </Focusable>
      </FocusRoot>
    </ModalRoot>
  );
}

export function openThemeDetailsModal(themeId: string, onClosed?: () => void): void {
  showModal(<ThemeDetailsModal themeId={themeId} />, window, { fnOnClose: onClosed });
}
