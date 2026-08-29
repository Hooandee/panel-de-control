import { ButtonItem, Focusable, ModalRoot, Navigation, showModal } from "@decky/ui";
import { LuExternalLink, LuSparkles } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { groupThemePatches } from "../themes/patchGroups";
import { useThemes } from "../themes/useThemes";
import { ThemePatchControl } from "./ThemePatchControl";
import { ConfirmDialog } from "./ConfirmDialog";
import { FocusRoot } from "./FocusRoot";

interface ThemeDetailsModalProps {
  themeId: string;
  closeModal?: () => void;
}

export function ThemeDetailsModal({ themeId, closeModal }: ThemeDetailsModalProps) {
  const { lang, t } = useI18n();
  const controller = useThemes();

  if (controller.loading) {
    return (
      <ModalRoot bAllowFullSize onCancel={closeModal} onEscKeypress={closeModal}>
        <FocusRoot><div style={{ padding: theme.space.lg, color: theme.color.textMuted }}>{t("themes.loading")}</div></FocusRoot>
      </ModalRoot>
    );
  }

  if (controller.snapshot.status !== "ready") {
    return (
      <ModalRoot bAllowFullSize onCancel={closeModal} onEscKeypress={closeModal}>
        <FocusRoot style={{ padding: theme.space.lg, color: theme.color.textPrimary }}>
          <div>{t(`themes.cssLoader.${controller.snapshot.status}`)}</div>
          <div style={{ marginTop: theme.space.md }}>
            <ButtonItem layout="below" onClick={() => void controller.refresh()}>{t("themes.retry")}</ButtonItem>
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

  const busy = controller.operation !== null && controller.operation.themeId === card.id;
  const groups = groupThemePatches(card.cssLoaderTheme?.patches ?? []);

  return (
    <ModalRoot bAllowFullSize onCancel={closeModal} onEscKeypress={closeModal}>
      <FocusRoot style={{ minHeight: "100%" }}>
      <Focusable style={{ minHeight: "100%", background: "radial-gradient(circle at 82% 6%, rgba(48,213,255,.14), transparent 30%), radial-gradient(circle at 4% 35%, rgba(255,45,176,.12), transparent 34%), #050507" }}>
        <div style={{ maxWidth: 980, margin: "0 auto", padding: "34px 42px 60px", color: theme.color.textPrimary }}>
          <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 24, marginBottom: 26 }}>
            <div>
              <div style={{ color: theme.color.accent, fontSize: theme.font.caption, fontWeight: 800, letterSpacing: 1.4, textTransform: "uppercase" }}>
                {t("themes.details.eyebrow")}
              </div>
              <h2 style={{ fontSize: 34, lineHeight: 1, margin: "8px 0 10px", letterSpacing: -1 }}>{card.catalog.name}</h2>
              <div style={{ color: theme.color.textMuted, maxWidth: 650, lineHeight: 1.45 }}>
                {t(card.catalog.descriptionKey)}
              </div>
              <div style={{ color: theme.color.textMuted, fontSize: theme.font.caption, marginTop: 9 }}>
                {card.catalog.author} · v{card.installedVersion ?? card.catalog.version}
              </div>
            </div>
            {card.installed && !card.active && (
              <div style={{ width: 220 }}>
                <ButtonItem layout="below" disabled={busy} onClick={() => void controller.activate(card.id)}>
                  <LuSparkles size={14} /> {t(busy ? "themes.action.activating" : "themes.action.activate")}
                </ButtonItem>
              </div>
            )}
            {card.active && (
              <div style={{ color: theme.color.ok, fontSize: theme.font.body, fontWeight: 800 }}>
                {t("themes.state.active")}
              </div>
            )}
          </div>

          {controller.error && (
            <div style={{ ...theme.card, padding: theme.space.md, marginBottom: theme.space.section, color: theme.color.warn }}>
              {controller.error}
            </div>
          )}

          {!card.installed && card.catalog.installSource ? (
            <div style={{ ...theme.card, padding: theme.space.lg }}>
              <div style={{ color: theme.color.textPrimary, fontWeight: 750 }}>{t("themes.install.ready")}</div>
              <div style={{ color: theme.color.textMuted, fontSize: theme.font.caption, lineHeight: 1.45, marginTop: theme.space.xs }}>
                {t("themes.install.ready.desc")}
              </div>
              <div style={{ marginTop: theme.space.md }}>
                <ButtonItem
                  layout="below"
                  disabled={busy}
                  onClick={() => showModal(
                    <ConfirmDialog
                      title={t("themes.install.confirm.title")}
                      desc={t("themes.install.confirm.desc", { name: card.catalog.name })}
                      confirmLabel={t("themes.install.confirm.ok")}
                      cancelLabel={t("themes.install.confirm.cancel")}
                      onConfirm={() => void controller.install(card.id)}
                    />,
                    window,
                  )}
                >
                  {t(busy ? "themes.action.installing" : "themes.action.install")}
                </ButtonItem>
              </div>
            </div>
          ) : !card.installed ? (
            <div style={{ ...theme.card, padding: theme.space.lg }}>
              <div style={{ color: theme.color.textPrimary, fontWeight: 750 }}>{t("themes.install.unavailable")}</div>
              <div style={{ color: theme.color.textMuted, fontSize: theme.font.caption, lineHeight: 1.45, marginTop: theme.space.xs }}>
                {t("themes.install.unavailable.desc")}
              </div>
              {card.catalog.projectUrl && (
                <div style={{ marginTop: theme.space.md }}>
                  <ButtonItem layout="below" onClick={() => Navigation.NavigateToExternalWeb(card.catalog.projectUrl!)}>
                    <LuExternalLink size={14} /> {t("themes.action.project")}
                  </ButtonItem>
                </div>
              )}
            </div>
          ) : groups.length === 0 ? (
            <div style={{ ...theme.card, padding: theme.space.lg, color: theme.color.textMuted }}>
              {t("themes.patches.empty")}
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
              {groups.map((group) => (
                <section key={group.id}>
                  <div style={{ ...theme.sectionLabel, margin: `0 0 ${theme.space.sm}px ${theme.space.xs}px` }}>
                    {t(`themes.group.${group.id}`)}
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
                    {group.patches.map((patch) => (
                      <ThemePatchControl
                        key={patch.name}
                        patch={patch}
                        disabled={busy}
                        lang={lang}
                        onChange={(value) => void controller.setPatch(card.id, patch.name, value)}
                      />
                    ))}
                  </div>
                </section>
              ))}
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
