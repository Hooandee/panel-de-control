import { ButtonItem, DialogButton, Focusable, ModalRoot, Navigation, showModal } from "@decky/ui";
import { type CSSProperties, useState } from "react";
import { LuDownload, LuPaintbrush, LuPower, LuRefreshCw, LuSparkles } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { groupThemePatches } from "../themes/patchGroups";
import { localizePublishedText } from "../themes/remotePublication";
import { themeCoverFor } from "../themes/themePresentation";
import { useThemes } from "../themes/useThemes";
import { FocusRoot } from "./FocusRoot";
import { ThemePatchControl } from "./ThemePatchControl";

interface ThemeDetailsModalProps {
  themeId: string;
  closeModal?: () => void;
}

interface ThemeOffer {
  kind: "install" | "update";
  version: string;
}

const THEME_CONTROL_RESET = `
[data-pdc-theme-settings] { color: ${theme.color.textPrimary} !important; }
[data-pdc-theme-settings] [data-pdc-theme-muted] { color: ${theme.color.textMuted} !important; }
[data-pdc-theme-settings] [data-pdc-theme-cover-header] { color: rgba(255,255,255,0.99) !important; }
[data-pdc-theme-settings] [data-pdc-theme-cover-header] [data-pdc-theme-muted] { color: rgba(255,255,255,0.92) !important; }
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

const COVER_IMAGE_STYLE: CSSProperties = {
  position: "absolute",
  inset: -2,
  zIndex: -2,
  width: "calc(100% + 4px)",
  height: "calc(100% + 4px)",
  objectFit: "cover",
  objectPosition: "center",
};

const COVER_GRADIENT_STYLE: CSSProperties = {
  position: "absolute",
  inset: 0,
  zIndex: -1,
  background: "linear-gradient(0deg, rgba(0,0,0,1) 0, rgba(0,0,0,0.96) 4px, rgba(0,0,0,0) 14px), linear-gradient(90deg, rgba(0,0,0,0.88) 0%, rgba(0,0,0,0.66) 54%, rgba(0,0,0,0.38) 100%), linear-gradient(0deg, rgba(0,0,0,0.92) 0%, rgba(0,0,0,0.58) 58%, rgba(0,0,0,0.12) 100%)",
};

const CONFIRMATION_SURFACE_STYLE: CSSProperties = {
  ...theme.card,
  padding: theme.space.md,
  marginBottom: theme.space.section,
  background: `linear-gradient(135deg, rgba(${theme.color.accentRgb},0.15), rgba(${theme.color.accentRgb},0.035) 48%, ${theme.color.surfaceRaised})`,
  boxShadow: `inset 0 0 0 1px rgba(${theme.color.accentRgb},0.25), 0 14px 32px rgba(0,0,0,0.2)`,
};

const CONFIRMATION_ICON_STYLE: CSSProperties = {
  width: 42,
  height: 42,
  borderRadius: theme.radius.sm,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  color: theme.color.accent,
  background: `rgba(${theme.color.accentRgb},0.16)`,
  boxShadow: `inset 0 0 0 1px rgba(${theme.color.accentRgb},0.22)`,
};

const VERSION_PILL_STYLE: CSSProperties = {
  alignSelf: "start",
  padding: "4px 9px",
  borderRadius: 999,
  color: theme.color.textPrimary,
  fontSize: theme.font.caption,
  whiteSpace: "nowrap",
  background: "rgba(255,255,255,0.055)",
  boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
};

const SECONDARY_CONFIRM_STYLE: CSSProperties = {
  minWidth: 120,
  borderRadius: theme.radius.sm,
  background: "rgba(255,255,255,0.028)",
  color: theme.color.textMuted,
  boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
};

const PRIMARY_CONFIRM_STYLE: CSSProperties = {
  minWidth: 142,
  borderRadius: theme.radius.sm,
  background: `linear-gradient(180deg, rgba(${theme.color.accentRgb},0.18), rgba(${theme.color.accentRgb},0.08))`,
  color: theme.color.textPrimary,
  fontWeight: 780,
  boxShadow: `inset 0 0 0 1px rgba(${theme.color.accentRgb},0.42), 0 7px 20px rgba(${theme.color.accentRgb},0.12)`,
};

function formatVersion(value: string): string {
  return value.toLowerCase().startsWith("v") ? value : `v${value}`;
}

interface ThemeInstallConfirmationProps {
  offer: ThemeOffer;
  displayName: string;
  actionsBlocked: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

function ThemeInstallConfirmation({
  offer,
  displayName,
  actionsBlocked,
  onCancel,
  onConfirm,
}: ThemeInstallConfirmationProps) {
  const { t } = useI18n();
  const updating = offer.kind === "update";

  return (
    <div role="group" aria-labelledby="theme-install-confirmation-title" style={CONFIRMATION_SURFACE_STYLE}>
      <div style={{ display: "grid", gridTemplateColumns: "42px minmax(0, 1fr) auto", alignItems: "center", gap: theme.space.md }}>
        <span aria-hidden style={CONFIRMATION_ICON_STYLE}>
          {updating ? <LuRefreshCw size={19} /> : <LuDownload size={19} />}
        </span>
        <div style={{ minWidth: 0 }}>
          <div id="theme-install-confirmation-title" style={{ fontSize: 18, lineHeight: 1.15, fontWeight: 780 }}>
            {t(updating ? "themes.update.confirm.title" : "themes.install.confirm.title", { name: displayName })}
          </div>
          <div data-pdc-theme-muted style={{ marginTop: 5, lineHeight: 1.4 }}>
            {t(updating ? "themes.update.confirm.desc" : "themes.install.confirm.desc")}
          </div>
        </div>
        <span style={VERSION_PILL_STYLE}>
          {t("themes.remote.card.version", { version: offer.version })}
        </span>
      </div>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: theme.space.sm, marginTop: theme.space.md, marginLeft: 54 }}>
        <DialogButton style={SECONDARY_CONFIRM_STYLE} onClick={onCancel}>
          {t("themes.install.confirm.cancel")}
        </DialogButton>
        <DialogButton style={PRIMARY_CONFIRM_STYLE} disabled={actionsBlocked} onClick={onConfirm}>
          <span style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 7 }}>
            {updating ? <LuRefreshCw size={15} aria-hidden /> : <LuDownload size={15} aria-hidden />}
            <span>{t(updating ? "themes.update.confirm.ok" : "themes.install.confirm.ok")}</span>
          </span>
        </DialogButton>
      </div>
    </div>
  );
}

export function ThemeDetailsModal({ themeId, closeModal }: ThemeDetailsModalProps) {
  const { lang, t } = useI18n();
  const controller = useThemes();
  const [confirmedVersion, setConfirmedVersion] = useState<string | null>(null);
  const [failedCover, setFailedCover] = useState<string>();
  const card = controller.cards.find((candidate) => candidate.id === themeId);

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
  const fullSizeLayout = card.installed && groups.length > 0;
  const availableCover = themeCoverFor(card.release);
  const cover = availableCover === failedCover ? undefined : availableCover;
  const offer: ThemeOffer | null = cssReady
    && card.installable
    && card.targetVersion
    && (!card.installed || card.updateAvailable)
    ? { kind: card.installed ? "update" : "install", version: card.targetVersion }
    : null;
  const activeConfirmation = offer
    && confirmedVersion === offer.version
    ? offer
    : null;
  const cancelOrClose = activeConfirmation ? () => setConfirmedVersion(null) : closeModal;

  return (
    <ModalRoot bAllowFullSize={fullSizeLayout} onCancel={cancelOrClose} onEscKeypress={cancelOrClose}>
      <FocusRoot style={fullSizeLayout ? { minHeight: "100%" } : undefined}>
        <Focusable style={fullSizeLayout ? { minHeight: "100%" } : undefined}>
          <div data-testid="theme-settings-content" data-pdc-theme-settings="true" style={{ maxWidth: fullSizeLayout ? 760 : 620, margin: "0 auto", padding: fullSizeLayout ? "8px 8px 54px" : "4px 8px 18px", color: theme.color.textPrimary }}>
            <style>{THEME_CONTROL_RESET}</style>
            <header data-pdc-theme-cover-header={cover ? "true" : undefined} style={{
              ...theme.card,
              position: "relative",
              isolation: "isolate",
              overflow: "hidden",
              display: "grid",
              gridTemplateColumns: card.installed ? "minmax(0, 1fr) minmax(150px, 220px)" : "minmax(0, 1fr)",
              alignItems: "center",
              gap: theme.space.lg,
              padding: fullSizeLayout ? theme.space.md : theme.space.lg,
              minHeight: cover ? (fullSizeLayout ? 126 : 138) : undefined,
              marginBottom: theme.space.md,
              background: `linear-gradient(135deg, rgba(${theme.color.accentRgb},0.11), ${theme.color.surfaceRaised} 58%)`,
            }}>
              {cover ? (
                <>
                  <img
                    data-testid="theme-details-cover"
                    src={cover}
                    alt=""
                    aria-hidden
                    draggable={false}
                    width={960}
                    height={240}
                    onError={() => setFailedCover(cover)}
                    style={COVER_IMAGE_STYLE}
                  />
                  <div
                    data-testid="theme-details-cover-gradient"
                    aria-hidden
                    style={COVER_GRADIENT_STYLE}
                  />
                </>
              ) : null}
              <div
                data-testid={cover ? "theme-details-cover-copy" : undefined}
                style={{
                  position: "relative",
                  display: "flex",
                  alignItems: "flex-start",
                  gap: theme.space.md,
                  minWidth: 0,
                  textShadow: cover ? "0 2px 10px rgba(0,0,0,0.9)" : undefined,
                }}
              >
                <span aria-hidden style={{
                  width: 42,
                  height: 42,
                  borderRadius: theme.radius.sm,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  flexShrink: 0,
                  color: cover ? "rgba(255,255,255,0.92)" : theme.color.accent,
                  background: cover ? "rgba(0,0,0,0.28)" : `rgba(${theme.color.accentRgb},0.14)`,
                  boxShadow: cover ? "inset 0 0 0 1px rgba(255,255,255,0.18)" : `inset 0 0 0 1px rgba(${theme.color.accentRgb},0.24)`,
                }}>
                  <LuPaintbrush size={20} />
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: theme.space.sm }}>
                    <h2 style={{ fontSize: fullSizeLayout ? 32 : 28, lineHeight: 1.05, margin: "1px 0 8px", letterSpacing: -0.8 }}>{displayName}</h2>
                    {!card.installed ? (
                      <span data-pdc-theme-muted style={{
                        flexShrink: 0,
                        padding: "3px 8px",
                        borderRadius: 999,
                        fontSize: theme.font.caption,
                        background: cover ? "rgba(0,0,0,0.32)" : "rgba(255,255,255,0.045)",
                        boxShadow: cover ? "inset 0 0 0 1px rgba(255,255,255,0.18)" : `inset 0 0 0 1px ${theme.color.hairline}`,
                      }}>
                        {t("themes.version.published", { version: formatVersion(card.release.publishedVersion) })}
                      </span>
                    ) : null}
                  </div>
                  <div data-pdc-theme-muted style={{ lineHeight: 1.45 }}>{description}</div>
                  {card.installed ? (
                    <div data-pdc-theme-muted style={{ display: "flex", flexWrap: "wrap", gap: 7, marginTop: 9, fontSize: theme.font.caption }}>
                      {card.installedVersion ? <span>{t("themes.version.installed", { version: formatVersion(card.installedVersion) })}</span> : null}
                      <span>{t("themes.version.published", { version: formatVersion(card.release.publishedVersion) })}</span>
                    </div>
                  ) : null}
                </div>
              </div>
              {card.installed ? (
                <div data-pdc-theme-action="true" style={{ position: "relative" }}>
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

            {!fullSizeLayout ? <div aria-hidden style={{ height: 1, margin: `0 ${theme.space.xs}px ${theme.space.md}px`, background: theme.color.hairline }} /> : null}

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

            {offer ? activeConfirmation ? (
              <ThemeInstallConfirmation
                offer={activeConfirmation}
                displayName={displayName}
                actionsBlocked={actionsBlocked}
                onCancel={() => setConfirmedVersion(null)}
                onConfirm={() => {
                  setConfirmedVersion(null);
                  void controller.install(card.id, { version: activeConfirmation.version });
                }}
              />
            ) : (
              <div
                role="group"
                aria-labelledby="theme-install-ready-label"
                style={{
                  ...STATUS_SURFACE,
                  ...theme.card,
                  ...(card.installed ? {} : { display: "flex", alignItems: "center", justifyContent: "space-between", gap: theme.space.md, padding: theme.space.sm }),
                  background: card.installed
                    ? theme.color.surfaceRaised
                    : `linear-gradient(90deg, rgba(${theme.color.accentRgb},0.09), rgba(${theme.color.accentRgb},0.025))`,
                  boxShadow: `inset 0 0 0 1px rgba(${theme.color.accentRgb},0.16)`,
                }}
              >
                <div id="theme-install-ready-label" style={{ display: "flex", alignItems: "center", gap: theme.space.sm, fontWeight: 750 }}>
                  {!card.installed ? (
                    <span aria-hidden style={{
                      width: 30,
                      height: 30,
                      borderRadius: theme.radius.sm,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      color: theme.color.accent,
                      background: `rgba(${theme.color.accentRgb},0.13)`,
                    }}>
                      <LuDownload size={16} />
                    </span>
                  ) : null}
                  <span>{t(card.installed ? "themes.update.ready" : "themes.install.ready")}</span>
                </div>
                <div style={{ marginTop: card.installed ? theme.space.md : 0, flexShrink: 0 }}>
                  <ButtonItem layout="below" disabled={actionsBlocked} onClick={() => setConfirmedVersion(offer.version)}>
                    {t(installing ? card.installed ? "themes.action.updating" : "themes.action.installing" : card.installed ? "themes.action.update" : "themes.action.install")}
                  </ButtonItem>
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
