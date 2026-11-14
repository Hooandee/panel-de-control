import { FC, ReactNode } from "react";
import { DialogButton } from "@decky/ui";
import { showModal } from "../navigation/showModal";
import { LuPower, LuEyeOff } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { NoticeActions, NoticeDialog, NoticeHeader, NoticeIcon, NoticeTitle } from "./dialogs/NoticeDialog";

interface Opts {
  moduleName: string;
  body?: ReactNode;
  onDisable: () => void;
  onHideInstead?: () => void;
}

const DisableModuleModal: FC<Opts & { closeModal?: () => void }> = ({ moduleName, body, onDisable, onHideInstead, closeModal }) => {
  const { t } = useI18n();
  const close = () => closeModal?.();
  return (
    <NoticeDialog closeModal={closeModal}>
      <NoticeHeader>
        <NoticeIcon background={theme.color.surfaceRaised} outline={theme.color.warn}>
          <LuPower size={26} color={theme.color.warn} />
        </NoticeIcon>
        <NoticeTitle>{t("customize.disable.title", { name: moduleName })}</NoticeTitle>
      </NoticeHeader>

      <div style={{ fontSize: theme.font.body, color: theme.color.textPrimary, lineHeight: 1.45, textAlign: "center" }}>
        {body ?? t("customize.disable.body")}
      </div>

      {onHideInstead && (
        <div style={{ display: "flex", gap: theme.space.sm, alignItems: "flex-start", padding: theme.space.md, borderRadius: theme.radius.sm, background: `rgba(${theme.color.accentRgb},0.06)`, boxShadow: `inset 0 0 0 1px ${theme.color.hairline}` }}>
          <LuEyeOff size={16} color={theme.color.accent} style={{ flex: "0 0 auto", marginTop: 1 }} />
          <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, lineHeight: 1.4 }}>
            {t("customize.disable.hint")}
          </div>
        </div>
      )}

      <NoticeActions>
        <DialogButton onClick={() => { onDisable(); close(); }}>
          {t("customize.disable")}
        </DialogButton>
        {onHideInstead && (
          <DialogButton onClick={() => { onHideInstead(); close(); }}>
            {t("customize.disable.hide")}
          </DialogButton>
        )}
        <DialogButton onClick={close}>
          {t("customize.disable.cancel")}
        </DialogButton>
      </NoticeActions>
    </NoticeDialog>
  );
};

export function openDisableModuleModal(opts: Opts): void {
  showModal(<DisableModuleModal {...opts} />, window);
}
