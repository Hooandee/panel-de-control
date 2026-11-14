import { FC } from "react";
import { DialogButton } from "@decky/ui";
import { showModal } from "../navigation/showModal";
import { LuZap } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { NoticeActions, NoticeDialog, NoticeFootnote, NoticeIcon, NoticeTitle } from "./dialogs/NoticeDialog";

interface Props {
  onTakeAll: () => void;
  closeModal?: () => void;
}

// Take-over modal: one gesture disables every rival. "Not now" closes; the
// persistent card carries on while the conflict lasts.
const TdpConflictModal: FC<Props> = ({ onTakeAll, closeModal }) => {
  const { t } = useI18n();
  return (
    <NoticeDialog closeModal={closeModal} centered>
      <NoticeIcon background={theme.color.warn}>
        <LuZap size={28} color={theme.color.onAccent} />
      </NoticeIcon>
      <NoticeTitle>{t("tdp.conflict.take.title")}</NoticeTitle>
      <div style={{ fontSize: theme.font.body, color: theme.color.textMuted, lineHeight: 1.45 }}>
        {t("tdp.conflict.take.body")}
      </div>
      <NoticeActions style={{ width: "100%", maxWidth: 300 }}>
        <DialogButton
          onClick={() => {
            onTakeAll();
            closeModal?.();
          }}
        >
          {t("tdp.conflict.take.confirm")}
        </DialogButton>
        <DialogButton onClick={() => closeModal?.()}>{t("tdp.conflict.take.later")}</DialogButton>
      </NoticeActions>
      <NoticeFootnote>{t("tdp.conflict.take.fine")}</NoticeFootnote>
    </NoticeDialog>
  );
};

export function openTdpConflictModal(onTakeAll: () => void): void {
  showModal(<TdpConflictModal onTakeAll={onTakeAll} />, window);
}
