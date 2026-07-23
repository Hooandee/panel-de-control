import { FC } from "react";
import { DialogButton, ModalRoot, PanelSectionRow, ToggleField, showModal } from "@decky/ui";
import { LuTriangleAlert } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { FocusRoot } from "./FocusRoot";

interface Props {
  enabled: boolean;
  onToggle: (enabled: boolean) => void;
}

/** Warn before taking over an unofficial EC channel. Only enables on confirm. */
const ConfirmModal: FC<{ onConfirm: () => void; closeModal?: () => void }> = ({ onConfirm, closeModal }) => {
  const { t } = useI18n();
  return (
    <ModalRoot onCancel={closeModal} onEscKeypress={closeModal}>
      <FocusRoot style={{ display: "flex", flexDirection: "column", gap: theme.space.md }}>
        <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, fontSize: 20, fontWeight: 700 }}>
          <LuTriangleAlert size={20} color={theme.color.warn} /> {t("fans.experimental.confirm.title")}
        </div>
        <div style={{ fontSize: theme.font.body, color: theme.color.textPrimary, lineHeight: 1.4 }}>
          {t("fans.experimental.confirm.desc")}
        </div>
        <div style={{ display: "flex", gap: theme.space.sm }}>
          <DialogButton style={{ flex: 1, minWidth: 0 }} onClick={() => { closeModal?.(); onConfirm(); }}>
            {t("fans.experimental.confirm.ok")}
          </DialogButton>
          <DialogButton style={{ flex: 1, minWidth: 0 }} onClick={() => closeModal?.()}>
            {t("fans.experimental.confirm.cancel")}
          </DialogButton>
        </div>
      </FocusRoot>
    </ModalRoot>
  );
};

/**
 * Opt-in for experimental EC fan control on devices whose only channel is
 * unofficial (Legion Go S). Off = read-only monitor; enabling asks for an explicit
 * confirm first. When on, the curve editor (and its reset) render below — the
 * section handles that; this card just carries the toggle + the note.
 */
export const ExperimentalFanCard: FC<Props> = ({ enabled, onToggle }) => {
  const { t } = useI18n();
  return (
    <PanelSectionRow>
      <div style={{ ...theme.card, padding: theme.space.md, overflow: "hidden", marginBottom: theme.space.card }}>
        <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, fontSize: theme.font.body, fontWeight: 700, color: theme.color.textPrimary }}>
          <LuTriangleAlert size={16} color={theme.color.warn} /> {t("fans.experimental.title")}
        </div>
        {!enabled && (
          <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, margin: `${theme.space.xs}px 0`, lineHeight: 1.4 }}>
            {t("fans.experimental.note")}
          </div>
        )}
        <ToggleField
          label={t("fans.experimental.toggle")}
          checked={enabled}
          bottomSeparator="none"
          onChange={(next: boolean) => {
            if (next) showModal(<ConfirmModal onConfirm={() => onToggle(true)} />);
            else onToggle(false);
          }}
        />
      </div>
    </PanelSectionRow>
  );
};
