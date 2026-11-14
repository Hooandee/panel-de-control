import { FC, ReactNode } from "react";
import { DialogButton } from "@decky/ui";
import { showModal } from "../navigation/showModal";
import { LuGauge, LuShieldCheck, LuTarget, LuZap } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { NoticeActions, NoticeDialog, NoticeFootnote, NoticeHeader, NoticeIcon, NoticeTitle } from "./dialogs/NoticeDialog";

interface Props {
  onConfirm: () => void;
  onCancel: () => void;
  levels?: boolean;
  closeModal?: () => void;
}

const Point: FC<{ icon: ReactNode; color: string; text: string }> = ({ icon, color, text }) => (
  <div style={{ display: "flex", gap: theme.space.sm, alignItems: "flex-start" }}>
    <div
      style={{
        flex: "0 0 auto",
        width: 26,
        height: 26,
        borderRadius: theme.radius.sm,
        background: `rgba(${theme.color.accentRgb},0.12)`,
        display: "grid",
        placeItems: "center",
        color,
      }}
    >
      {icon}
    </div>
    <div style={{ fontSize: theme.font.body, color: theme.color.textPrimary, lineHeight: 1.4 }}>
      {text}
    </div>
  </div>
);

const AutoTdpNoticeModal: FC<Props> = ({ onConfirm, onCancel, levels, closeModal }) => {
  const { t } = useI18n();
  const unit = levels ? ".level" : "";
  return (
    <NoticeDialog closeModal={closeModal}>
      <NoticeHeader>
        <NoticeIcon background={theme.color.accent}>
          <LuZap size={28} color={theme.color.onAccent} />
        </NoticeIcon>
        <NoticeTitle>{t("tdp.autotdp.title")}</NoticeTitle>
        <span
          style={{
            padding: "2px 8px",
            borderRadius: 999,
            color: theme.color.warn,
            boxShadow: `inset 0 0 0 1px ${theme.color.warn}`,
            fontSize: theme.font.caption,
            fontWeight: 700,
          }}
        >
          {t("tdp.auto.experimental")}
        </span>
      </NoticeHeader>

      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.md }}>
        <Point icon={<LuTarget size={15} />} color={theme.color.accent} text={t("tdp.autotdp.p1")} />
        <Point icon={<LuGauge size={15} />} color={theme.color.accent} text={t(`tdp.autotdp.p2${unit}`)} />
        <Point icon={<LuShieldCheck size={15} />} color={theme.color.ok} text={t(`tdp.autotdp.p3${unit}`)} />
      </div>

      <NoticeActions>
        <DialogButton
          onClick={() => {
            onConfirm();
            closeModal?.();
          }}
        >
          {t("tdp.autotdp.confirm")}
        </DialogButton>
        <DialogButton
          onClick={() => {
            onCancel();
            closeModal?.();
          }}
        >
          {t("tdp.autotdp.cancel")}
        </DialogButton>
      </NoticeActions>
      <NoticeFootnote>{t("tdp.autotdp.once")}</NoticeFootnote>
    </NoticeDialog>
  );
};

export function openAutoTdpNoticeModal(opts: { onConfirm: () => void; onCancel: () => void; levels?: boolean }): void {
  showModal(<AutoTdpNoticeModal onConfirm={opts.onConfirm} onCancel={opts.onCancel} levels={opts.levels} />, window);
}
