import { ButtonItem, Focusable, ModalRoot, Navigation, showModal } from "@decky/ui";
import { type CSSProperties, useState } from "react";
import { LuExternalLink, LuPower, LuRefreshCw, LuSparkles } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { groupThemePatches } from "../themes/patchGroups";
import { useThemes } from "../themes/useThemes";
import { ThemePatchControl } from "./ThemePatchControl";
import { FocusRoot } from "./FocusRoot";

interface ThemeDetailsModalProps {
  themeId: string;
  closeModal?: () => void;
}

const THEME_PATCH_CHROME_RESET = `
[data-pdc-theme-settings] {
  color: var(--hdg-text-primary, ${theme.color.textPrimary}) !important;
}
[data-pdc-theme-settings] [data-pdc-theme-muted] {
  color: var(--hdg-text-secondary, ${theme.color.textMuted}) !important;
}
[data-pdc-theme-settings] [data-pdc-theme-accent-ink] {
  color: var(--hdg-accent-ink, ${theme.color.ok}) !important;
}
[data-pdc-theme-settings] [data-pdc-theme-warning] {
  color: var(--hdg-warning-ink, var(--hdg-critical, ${theme.color.warn})) !important;
}
[data-pdc-theme-settings] [data-pdc-theme-patch-control] {
  background: var(--hdg-settings-row-surface, ${theme.color.surfaceRaised}) !important;
  box-shadow: inset 0 0 0 1px var(--hdg-glass-stroke-soft, ${theme.color.hairline}) !important;
  color: var(--hdg-text-primary, ${theme.color.textPrimary}) !important;
}
[data-pdc-theme-settings] [data-pdc-theme-status-surface] {
  background: var(--hdg-settings-row-surface, ${theme.color.surfaceRaised}) !important;
  box-shadow: inset 0 0 0 1px var(--hdg-glass-stroke-soft, ${theme.color.hairline}) !important;
  color: var(--hdg-text-primary, ${theme.color.textPrimary}) !important;
}
[data-pdc-theme-settings] [data-pdc-theme-patch-primary] {
  color: var(--hdg-text-primary, ${theme.color.textPrimary}) !important;
}
[data-pdc-theme-settings] [data-pdc-theme-patch-muted] {
  color: var(--hdg-text-secondary, ${theme.color.textMuted}) !important;
}
[data-pdc-theme-settings] [data-pdc-theme-patch-accent] {
  color: var(--hdg-accent-ink, ${theme.color.accent}) !important;
}
[data-pdc-theme-settings] [data-pdc-theme-patch-control] > .Panel,
[data-pdc-theme-settings] [data-pdc-theme-patch-control] > div {
  background: transparent !important;
  background-image: none !important;
  border: 0 !important;
  border-radius: 0 !important;
  box-sizing: border-box !important;
  margin: 0 !important;
  padding: 0 !important;
  width: 100% !important;
  color: inherit !important;
}
[data-pdc-theme-settings] [data-pdc-theme-patch-control] > .Panel:not(.gpfocus),
[data-pdc-theme-settings] [data-pdc-theme-patch-control] > div:not(.gpfocus) {
  box-shadow: none !important;
}
[data-pdc-theme-settings] [data-pdc-theme-slider]
  .Panel.Focusable.gpfocuswithin:has(.SliderControlPanelGroup.gpfocus .SliderHandle),
[data-pdc-theme-settings] [data-pdc-theme-slider]
  .Panel.Focusable.gpfocuswithin:has([role="slider"].gpfocus .SliderHandle) {
  background: transparent !important;
  border-color: transparent !important;
  box-shadow: none !important;
  outline: 0 !important;
}
[data-pdc-theme-settings] [data-pdc-theme-slider]
  .Panel.Focusable.gpfocuswithin:has(.SliderControlPanelGroup.gpfocus .SliderHandle)::before,
[data-pdc-theme-settings] [data-pdc-theme-slider]
  .Panel.Focusable.gpfocuswithin:has(.SliderControlPanelGroup.gpfocus .SliderHandle)::after,
[data-pdc-theme-settings] [data-pdc-theme-slider]
  .Panel.Focusable.gpfocuswithin:has([role="slider"].gpfocus .SliderHandle)::before,
[data-pdc-theme-settings] [data-pdc-theme-slider]
  .Panel.Focusable.gpfocuswithin:has([role="slider"].gpfocus .SliderHandle)::after {
  content: none !important;
  box-shadow: none !important;
  outline: 0 !important;
}
[data-pdc-theme-settings] [data-pdc-theme-slider]
  :is(.SliderControlPanelGroup, [role="slider"]).gpfocus:has(.SliderHandle) {
  background: transparent !important;
  border: 0 !important;
  box-shadow: none !important;
  filter: none !important;
  outline: 0 !important;
}
[data-pdc-theme-settings] [data-pdc-theme-slider]
  :is(.SliderControlPanelGroup, [role="slider"]).gpfocus:has(.SliderHandle)::before,
[data-pdc-theme-settings] [data-pdc-theme-slider]
  :is(.SliderControlPanelGroup, [role="slider"]).gpfocus:has(.SliderHandle)::after {
  box-shadow: none !important;
  outline: 0 !important;
}
html:root #GamepadUI_Full_Root [data-pdc-theme-settings] [data-pdc-theme-slider]
  .SliderControlPanelGroup.gpfocus:has(.SliderHandle) :is(.SliderHandle, .SliderHandleFocusPop),
html:root #GamepadUI_Full_Root [data-pdc-theme-settings] [data-pdc-theme-slider]
  [role="slider"].gpfocus:has(.SliderHandle) :is(.SliderHandle, .SliderHandleFocusPop) {
  box-shadow:
    0 0 0 4px var(--hdg-slider-attention-ring, var(--hdg-focus-ring, ${theme.color.accent})),
    0 0 14px var(--hdg-accent-glow, rgba(78,161,255,0.34)) !important;
}
[data-pdc-theme-settings] [data-pdc-theme-action] > div {
  background: transparent !important;
  box-shadow: none !important;
  margin: 0 !important;
  padding: 0 !important;
}
`;

const statusSurfaceStyle: CSSProperties = {
  borderRadius: theme.radius.md,
  minWidth: 0,
};

function formatThemeVersion(value: string): string {
  return value.toLowerCase().startsWith("v") ? value : `v${value}`;
}

export function ThemeDetailsModal({ themeId, closeModal }: ThemeDetailsModalProps) {
  const { lang, t } = useI18n();
  const controller = useThemes();
  const [confirmation, setConfirmation] = useState<{
    kind: "install" | "update";
    version: string;
    source: "bundled" | "official-remote";
  } | null>(null);

  if (controller.loading) {
    return (
      <ModalRoot bAllowFullSize onCancel={closeModal} onEscKeypress={closeModal}>
        <FocusRoot>
          <div role="status" aria-live="polite" style={{ padding: theme.space.lg, color: theme.color.textMuted }}>
            {t("themes.loading")}
          </div>
        </FocusRoot>
      </ModalRoot>
    );
  }

  if (controller.snapshot.status !== "ready") {
    const recovering = controller.operation?.kind === "recovering";
    const checking = recovering || controller.refreshing;
    return (
      <ModalRoot bAllowFullSize onCancel={closeModal} onEscKeypress={closeModal}>
        <FocusRoot style={{ padding: theme.space.lg, color: theme.color.textPrimary }}>
          <div role="status" aria-live="polite">{t(`themes.cssLoader.${controller.snapshot.status}`)}</div>
          {controller.recoveryBlocked && (
            <div style={{ marginTop: theme.space.sm, color: theme.color.warn }}>
              {t("themes.recovery.blocked")}
            </div>
          )}
          <div style={{ marginTop: theme.space.md }}>
            <ButtonItem layout="below" disabled={checking} onClick={() => void controller.refresh()}>
              {t(checking ? "themes.loading" : "themes.retry")}
            </ButtonItem>
          </div>
        </FocusRoot>
      </ModalRoot>
    );
  }

  const card = controller.cards.find((candidate) => candidate.id === themeId);

  if (!card) {
    return (
      <ModalRoot bAllowFullSize onCancel={closeModal} onEscKeypress={closeModal}>
        <FocusRoot><div style={{ padding: theme.space.lg, color: theme.color.warn }}>{t("themes.details.unavailable")}</div></FocusRoot>
      </ModalRoot>
    );
  }

  const operationBusy = controller.operation !== null;
  const actionsBlocked = operationBusy || controller.recoveryBlocked;
  const recovering = controller.operation?.kind === "recovering";
  const installing = controller.operation?.kind === "installing" && controller.operation.themeId === card.id;
  const activating = controller.operation?.kind === "activating" && controller.operation.themeId === card.id;
  const deactivating = controller.operation?.kind === "deactivating" && controller.operation.themeId === card.id;
  const displayName = t(card.catalog.nameKey);
  const groups = groupThemePatches(card.cssLoaderTheme?.patches ?? []);
  const releaseNote = card.releaseNotes?.[lang]
    ?? card.releaseNotes?.en
    ?? card.releaseNotes?.es
    ?? card.releaseNotes?.it;
  const cancelOrClose = confirmation
    ? () => setConfirmation(null)
    : closeModal;

  return (
    <ModalRoot bAllowFullSize onCancel={cancelOrClose} onEscKeypress={cancelOrClose}>
      <FocusRoot style={{ minHeight: "100%" }}>
        <Focusable style={{ minHeight: "100%" }}>
          <div
            data-testid="theme-settings-content"
            data-pdc-theme-settings="true"
            style={{ maxWidth: 760, margin: "0 auto", padding: "8px 8px 54px", color: theme.color.textPrimary }}
          >
            <style>{THEME_PATCH_CHROME_RESET}</style>
            <div
              data-testid="theme-settings-header"
              style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 220px", alignItems: "center", gap: theme.space.lg, marginBottom: 22 }}
            >
              <div style={{ minWidth: 0 }}>
                <div style={{ color: theme.color.accent, fontSize: theme.font.caption, fontWeight: 800, letterSpacing: 1.4, textTransform: "uppercase" }}>
                  {t("themes.details.eyebrow")}
                </div>
                <h2 style={{ fontSize: 34, lineHeight: 1, margin: "8px 0 10px", letterSpacing: -1 }}>{displayName}</h2>
                <div data-pdc-theme-muted style={{ color: theme.color.textMuted, maxWidth: 650, lineHeight: 1.45 }}>
                  {t(card.catalog.descriptionKey)}
                </div>
                <div data-pdc-theme-muted style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6, color: theme.color.textMuted, fontSize: theme.font.caption, marginTop: 9 }}>
                  <span>{card.catalog.author}</span>
                  {card.installedVersion && (
                    <span>{t("themes.version.installed", {
                      version: formatThemeVersion(card.installedVersion),
                    })}</span>
                  )}
                  {card.publishedVersion && (
                    <span>{t("themes.version.published", {
                      version: formatThemeVersion(card.publishedVersion),
                    })}</span>
                  )}
                  {card.active && (
                    <span data-pdc-theme-accent-ink style={{ color: theme.color.ok, fontWeight: 800 }}>· {t("themes.state.active")}</span>
                  )}
                </div>
              </div>
              {card.installed && !card.active && (
                <div
                  data-testid="theme-settings-action"
                  data-pdc-theme-action="true"
                  style={{ width: 220, maxWidth: "100%" }}
                >
                  <ButtonItem layout="below" disabled={actionsBlocked} onClick={() => void controller.activate(card.id)}>
                    <LuSparkles size={14} aria-hidden /> {t(activating ? "themes.action.activating" : "themes.action.activate")}
                  </ButtonItem>
                </div>
              )}
              {card.active && (
                <div
                  data-testid="theme-settings-action"
                  data-pdc-theme-action="true"
                  style={{ width: 220, maxWidth: "100%" }}
                >
                  <ButtonItem layout="below" disabled={actionsBlocked} onClick={() => void controller.deactivate(card.id)}>
                    <LuPower size={14} aria-hidden /> {t(deactivating ? "themes.action.deactivating" : "themes.action.deactivate")}
                  </ButtonItem>
                </div>
              )}
            </div>

            {recovering && (
              <div
                data-pdc-theme-status-surface="true"
                role="status"
                aria-live="polite"
                style={{ ...statusSurfaceStyle, padding: theme.space.md, marginBottom: theme.space.section }}
              >
                <span data-pdc-theme-muted>{t("themes.recovering")}</span>
              </div>
            )}

            {controller.error && (
              <div
                data-pdc-theme-status-surface="true"
                role="alert"
                style={{ ...statusSurfaceStyle, padding: theme.space.md, marginBottom: theme.space.section }}
              >
                <div data-pdc-theme-warning style={{ color: theme.color.warn }}>
                  {t(controller.recoveryBlocked
                    ? "themes.recovery.blocked"
                    : "themes.operation.failed")}
                </div>
                <div style={{ marginTop: theme.space.sm }}>
                  <ButtonItem layout="below" disabled={operationBusy || controller.refreshing} onClick={() => void controller.refresh()}>
                    <LuRefreshCw size={14} aria-hidden /> {t(controller.refreshing ? "themes.loading" : "themes.retry")}
                  </ButtonItem>
                </div>
              </div>
            )}

            {controller.publication.status === "checking" && (
              <div
                data-pdc-theme-status-surface="true"
                role="status"
                aria-live="polite"
                style={{ ...statusSurfaceStyle, padding: theme.space.md, marginBottom: theme.space.section }}
              >
                <span data-pdc-theme-muted>{t("themes.remote.checking")}</span>
              </div>
            )}

            {(controller.publication.status === "temporarily-unavailable"
              || controller.publication.status === "recoverable-failure") && (
              <div
                data-pdc-theme-status-surface="true"
                style={{ ...statusSurfaceStyle, padding: theme.space.md, marginBottom: theme.space.section }}
              >
                <div data-pdc-theme-muted>{t("themes.remote.unavailable")}</div>
                <div style={{ marginTop: theme.space.sm }}>
                  <ButtonItem
                    layout="below"
                    disabled={operationBusy}
                    onClick={() => void controller.refreshPublication()}
                  >
                    <LuRefreshCw size={14} aria-hidden /> {t("themes.remote.retry")}
                  </ButtonItem>
                </div>
              </div>
            )}

            {card.publicationCompatibility && card.publicationCompatibility !== "compatible" && (
              <div
                data-pdc-theme-status-surface="true"
                style={{ ...statusSurfaceStyle, padding: theme.space.md, marginBottom: theme.space.section }}
              >
                <div data-pdc-theme-warning style={{ color: theme.color.warn }}>
                  {t(`themes.remote.${card.publicationCompatibility}`)}
                </div>
              </div>
            )}

            {releaseNote && (
              <div
                data-pdc-theme-status-surface="true"
                style={{ ...statusSurfaceStyle, padding: theme.space.md, marginBottom: theme.space.section }}
              >
                <div style={{ fontWeight: 750 }}>{t("themes.remote.notes")}</div>
                <div data-pdc-theme-muted style={{ marginTop: theme.space.xs, color: theme.color.textMuted, lineHeight: 1.45 }}>
                  {releaseNote}
                </div>
              </div>
            )}

            {installing && (
              <div
                data-pdc-theme-status-surface="true"
                role="status"
                aria-live="polite"
                style={{ ...statusSurfaceStyle, padding: theme.space.md, marginBottom: theme.space.section }}
              >
                <span data-pdc-theme-muted>{t(
                  card.preferredInstallSource === "official-remote"
                    ? "themes.remote.preparing"
                    : "themes.action.installing",
                )}</span>
              </div>
            )}

            {confirmation && (
              <div
                data-pdc-theme-status-surface="true"
                role="group"
                aria-labelledby="theme-install-confirmation-title"
                style={{ ...statusSurfaceStyle, padding: theme.space.lg, marginBottom: theme.space.section }}
              >
                <div id="theme-install-confirmation-title" style={{ fontWeight: 750 }}>
                  {t(confirmation.kind === "update"
                    ? "themes.update.confirm.title"
                    : "themes.install.confirm.title")}
                </div>
                <div data-pdc-theme-muted style={{ color: theme.color.textMuted, lineHeight: 1.45, marginTop: theme.space.xs }}>
                  {t(confirmation.kind === "update"
                    ? "themes.update.confirm.desc"
                    : "themes.install.confirm.desc", { name: displayName })}
                </div>
                <div style={{ display: "flex", gap: theme.space.sm, marginTop: theme.space.md }}>
                  <ButtonItem
                    layout="below"
                    disabled={actionsBlocked}
                    onClick={() => {
                      setConfirmation(null);
                      void controller.install(card.id, {
                        version: confirmation.version,
                        source: confirmation.source,
                      });
                    }}
                  >
                    {t(confirmation.kind === "update"
                      ? "themes.update.confirm.ok"
                      : "themes.install.confirm.ok")}
                  </ButtonItem>
                  <ButtonItem layout="below" disabled={operationBusy} onClick={() => setConfirmation(null)}>
                    {t("themes.install.confirm.cancel")}
                  </ButtonItem>
                </div>
              </div>
            )}

            {card.installed && card.updateAvailable && (
              <div data-pdc-theme-status-surface="true" style={{ ...statusSurfaceStyle, padding: theme.space.lg, marginBottom: theme.space.section }}>
                <div style={{ fontWeight: 750 }}>{t("themes.update.ready")}</div>
                <div data-pdc-theme-muted style={{ color: theme.color.textMuted, fontSize: theme.font.caption, lineHeight: 1.45, marginTop: theme.space.xs }}>
                  {t("themes.update.ready.desc", {
                    installed: card.installedVersion ? formatThemeVersion(card.installedVersion) : "—",
                    available: card.targetVersion ? formatThemeVersion(card.targetVersion) : "—",
                  })}
                </div>
                {card.preferredInstallSource ? (
                  <div style={{ marginTop: theme.space.md }}>
                    <ButtonItem
                      layout="below"
                      disabled={actionsBlocked}
                      onClick={() => card.targetVersion && card.preferredInstallSource
                        ? setConfirmation({
                          kind: "update",
                          version: card.targetVersion,
                          source: card.preferredInstallSource,
                        })
                        : undefined}
                    >
                      <LuRefreshCw size={14} aria-hidden /> {t(installing ? "themes.action.updating" : "themes.action.update")}
                    </ButtonItem>
                  </div>
                ) : (
                  <div data-pdc-theme-muted style={{ color: theme.color.textMuted, fontSize: theme.font.caption, lineHeight: 1.45, marginTop: theme.space.md }}>
                    {t("themes.update.unavailable.desc")}
                  </div>
                )}
              </div>
            )}

            {!card.installed && card.preferredInstallSource ? (
              <div data-pdc-theme-status-surface="true" style={{ ...statusSurfaceStyle, padding: theme.space.lg }}>
                <div style={{ fontWeight: 750 }}>{t("themes.install.ready")}</div>
                <div data-pdc-theme-muted style={{ color: theme.color.textMuted, fontSize: theme.font.caption, lineHeight: 1.45, marginTop: theme.space.xs }}>
                  {t("themes.install.ready.desc")}
                </div>
                <div style={{ marginTop: theme.space.md }}>
                  <ButtonItem
                    layout="below"
                    disabled={actionsBlocked}
                    onClick={() => card.targetVersion && card.preferredInstallSource
                      ? setConfirmation({
                        kind: "install",
                        version: card.targetVersion,
                        source: card.preferredInstallSource,
                      })
                      : undefined}
                  >
                    {t(installing ? "themes.action.installing" : "themes.action.install")}
                  </ButtonItem>
                </div>
              </div>
            ) : !card.installed ? (
              <div data-pdc-theme-status-surface="true" style={{ ...statusSurfaceStyle, padding: theme.space.lg }}>
                <div style={{ fontWeight: 750 }}>{t("themes.install.unavailable")}</div>
                <div data-pdc-theme-muted style={{ color: theme.color.textMuted, fontSize: theme.font.caption, lineHeight: 1.45, marginTop: theme.space.xs }}>
                  {t("themes.install.unavailable.desc")}
                </div>
                {card.catalog.projectUrl && (
                  <div style={{ marginTop: theme.space.md }}>
                    <ButtonItem layout="below" onClick={() => Navigation.NavigateToExternalWeb(card.catalog.projectUrl!)}>
                      <LuExternalLink size={14} aria-hidden /> {t("themes.action.project")}
                    </ButtonItem>
                  </div>
                )}
              </div>
            ) : groups.length === 0 ? (
              <div data-pdc-theme-status-surface="true" style={{ ...statusSurfaceStyle, padding: theme.space.lg }}>
                <span data-pdc-theme-muted>{t("themes.patches.empty")}</span>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
                {groups.map((group) => {
                  const headingId = `theme-patch-group-${group.id}`;
                  return (
                    <section
                      key={group.id}
                      aria-labelledby={headingId}
                      style={{ minWidth: 0 }}
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 6,
                          minHeight: 28,
                          padding: "0 2px",
                          marginBottom: theme.space.sm,
                        }}
                      >
                        <span
                          aria-hidden
                          style={{
                            width: 2,
                            height: 14,
                            flex: "0 0 auto",
                            borderRadius: 2,
                            background: theme.color.accent,
                          }}
                        />
                        <h3
                          id={headingId}
                          data-pdc-theme-muted
                          style={{
                            flex: 1,
                            minWidth: 0,
                            margin: 0,
                            color: theme.color.textMuted,
                            fontSize: theme.font.caption,
                            fontWeight: 700,
                            letterSpacing: 0.5,
                            textTransform: "uppercase",
                          }}
                        >
                          {t(`themes.group.${group.id}`)}
                        </h3>
                        <span
                          aria-hidden
                          data-pdc-theme-muted
                          style={{
                            minWidth: 16,
                            color: theme.color.textMuted,
                            fontSize: theme.font.caption,
                            fontVariantNumeric: "tabular-nums",
                            textAlign: "right",
                          }}
                        >
                          {group.patches.length}
                        </span>
                      </div>
                      <div role="list" style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
                        {group.patches.map((patch) => (
                          <div
                            key={patch.name}
                            role="listitem"
                            style={{ minWidth: 0 }}
                          >
                            <ThemePatchControl
                              patch={patch}
                              disabled={actionsBlocked}
                              lang={lang}
                              onChange={(value) => void controller.setPatch(card.id, patch.name, value)}
                            />
                          </div>
                        ))}
                      </div>
                    </section>
                  );
                })}
              </div>
            )}
          </div>
        </Focusable>
      </FocusRoot>
    </ModalRoot>
  );
}

export function openThemeDetailsModal(themeId: string, onClosed?: () => void): void {
  showModal(<ThemeDetailsModal themeId={themeId} />, window, { fnOnClose: onClosed });
}
