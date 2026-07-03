import { FC } from "react";
import { DialogButton, ModalRoot, PanelSectionRow, showModal } from "@decky/ui";
import { LuLightbulb, LuStore } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import type { ColoresCardState } from "../system/colores";

interface Props {
  state: ColoresCardState;
  onInstall: () => void;
  onOpen: () => void;
  onOpenStore: () => void;
}

/** Confirm before downloading + installing software from GitHub. */
const ColoresInstallModal: FC<{ onConfirm: () => void; closeModal?: () => void }> = ({
  onConfirm,
  closeModal,
}) => {
  const { t } = useI18n();
  return (
    <ModalRoot onCancel={closeModal} onEscKeypress={closeModal}>
      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.md }}>
        <div style={{ fontSize: 20, fontWeight: 700 }}>{t("system.rgb.confirm.title")}</div>
        <div style={{ fontSize: theme.font.body, color: theme.color.textPrimary, lineHeight: 1.4 }}>
          {t("system.rgb.confirm.desc")}
        </div>
        <div style={{ display: "flex", gap: theme.space.sm }}>
          <DialogButton
            style={{ flex: 1, minWidth: 0 }}
            onClick={() => {
              closeModal?.();
              onConfirm();
            }}
          >
            {t("system.rgb.confirm.ok")}
          </DialogButton>
          <DialogButton style={{ flex: 1, minWidth: 0 }} onClick={() => closeModal?.()}>
            {t("system.rgb.confirm.cancel")}
          </DialogButton>
        </div>
      </div>
    </ModalRoot>
  );
};

/**
 * RGB-lighting integration card (Sistema). Bridges to the sibling Colores plugin:
 * opens its panel if installed, or installs it from its GitHub release (with a
 * confirm). Never rendered on Steam Deck (no RGB LEDs) — the section gates on
 * `hasRgb`; a "hidden" state here is just a defensive guard.
 */
export const ColoresCard: FC<Props> = ({ state, onInstall, onOpen, onOpenStore }) => {
  const { t } = useI18n();
  if (state === "hidden") return null;

  const installed = state === "open";
  const desc = installed ? t("system.rgb.desc.installed") : t("system.rgb.desc.install");
  // One full-width button shape for every state (matches the ValueBar/updater buttons).
  const btn = { width: "100%", minWidth: 0 } as const;

  return (
    <PanelSectionRow>
      <div style={{ ...theme.card, padding: theme.space.md, overflow: "hidden", marginBottom: 6 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: theme.space.xs,
            fontSize: theme.font.body,
            fontWeight: 700,
            color: theme.color.textPrimary,
          }}
        >
          <LuLightbulb size={16} color={theme.color.accent} /> {t("system.rgb.title")}
        </div>
        <div
          style={{
            fontSize: theme.font.caption,
            color: state === "error" ? theme.color.warn : theme.color.textMuted,
            margin: `${theme.space.xs}px 0 ${theme.space.md}px`,
            lineHeight: 1.4,
          }}
        >
          {state === "error" ? t("system.rgb.error") : desc}
        </div>

        {state === "open" && (
          <DialogButton style={btn} onClick={onOpen}>
            {t("system.rgb.open")}
          </DialogButton>
        )}

        {state === "install" && (
          <DialogButton
            style={btn}
            onClick={() => showModal(<ColoresInstallModal onConfirm={onInstall} />)}
          >
            {t("system.rgb.install")}
          </DialogButton>
        )}

        {state === "installing" && (
          <DialogButton disabled style={btn} onClick={() => {}}>
            {t("system.rgb.installing")}
          </DialogButton>
        )}

        {state === "error" && (
          <DialogButton
            style={{ ...btn, display: "flex", alignItems: "center", justifyContent: "center", gap: theme.space.xs }}
            onClick={onOpenStore}
          >
            <LuStore size={14} /> {t("system.rgb.store")}
          </DialogButton>
        )}
      </div>
    </PanelSectionRow>
  );
};
