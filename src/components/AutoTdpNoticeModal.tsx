import { FC, ReactNode } from "react";
import { ModalRoot, showModal, Focusable, DialogButton } from "@decky/ui";
import { LuGauge, LuShieldCheck, LuTarget, LuZap } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { FocusRoot } from "./FocusRoot";

interface Props {
  onConfirm: () => void;
  onCancel: () => void;
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

const AutoTdpNoticeBody: FC<Props> = ({ onConfirm, onCancel, closeModal }) => {
  const { t } = useI18n();
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: theme.space.md,
        maxWidth: 420,
        margin: "0 auto",
        padding: theme.space.lg,
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: theme.space.xs }}>
        <div
          style={{
            width: 56,
            height: 56,
            borderRadius: theme.radius.md,
            background: theme.color.accent,
            display: "grid",
            placeItems: "center",
          }}
        >
          <LuZap size={28} color={theme.color.onAccent} />
        </div>
        <div style={{ fontSize: theme.font.value, fontWeight: 700, color: theme.color.textPrimary }}>
          {t("tdp.autotdp.title")}
        </div>
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
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.md }}>
        <Point icon={<LuTarget size={15} />} color={theme.color.accent} text={t("tdp.autotdp.p1")} />
        <Point icon={<LuGauge size={15} />} color={theme.color.accent} text={t("tdp.autotdp.p2")} />
        <Point icon={<LuShieldCheck size={15} />} color={theme.color.ok} text={t("tdp.autotdp.p3")} />
      </div>

      <Focusable style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
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
      </Focusable>
      <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, textAlign: "center" }}>
        {t("tdp.autotdp.once")}
      </div>
    </div>
  );
};

const AutoTdpNoticeModal: FC<Props> = ({ onConfirm, onCancel, closeModal }) => (
  <ModalRoot closeModal={closeModal} bAllowFullSize>
    <FocusRoot>
      <AutoTdpNoticeBody onConfirm={onConfirm} onCancel={onCancel} closeModal={closeModal} />
    </FocusRoot>
  </ModalRoot>
);

export function openAutoTdpNoticeModal(opts: { onConfirm: () => void; onCancel: () => void }): void {
  showModal(<AutoTdpNoticeModal onConfirm={opts.onConfirm} onCancel={opts.onCancel} />, window);
}
