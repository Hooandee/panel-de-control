import { FC } from "react";
import { ModalRoot, showModal, Focusable, DialogButton } from "@decky/ui";
import { LuZap } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { FocusRoot } from "./FocusRoot";

interface Props {
  onTakeAll: () => void;
  closeModal?: () => void;
}

// Full-screen first-run take-over: shown once when a TDP conflict is first
// detected. Assertive by design — one gesture ("turn them off and let me manage")
// disables every rival. "Not now" closes; the persistent card keeps nagging while
// the conflict lasts.
const TdpConflictBody: FC<Props> = ({ onTakeAll, closeModal }) => {
  const { t } = useI18n();
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        textAlign: "center",
        gap: theme.space.md,
        maxWidth: 420,
        margin: "0 auto",
        padding: theme.space.lg,
      }}
    >
      <div
        style={{
          width: 56,
          height: 56,
          borderRadius: theme.radius.md,
          background: theme.color.warn,
          display: "grid",
          placeItems: "center",
        }}
      >
        <LuZap size={28} color={theme.color.onAccent} />
      </div>
      <div style={{ fontSize: theme.font.value, fontWeight: 700, color: theme.color.textPrimary }}>
        {t("tdp.conflict.take.title")}
      </div>
      <div style={{ fontSize: theme.font.body, color: theme.color.textMuted, lineHeight: 1.45 }}>
        {t("tdp.conflict.take.body")}
      </div>
      <Focusable style={{ display: "flex", flexDirection: "column", gap: theme.space.sm, width: "100%", maxWidth: 300 }}>
        <DialogButton
          onClick={() => {
            onTakeAll();
            closeModal?.();
          }}
        >
          {t("tdp.conflict.take.confirm")}
        </DialogButton>
        <DialogButton onClick={() => closeModal?.()}>{t("tdp.conflict.take.later")}</DialogButton>
      </Focusable>
      <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
        {t("tdp.conflict.take.fine")}
      </div>
    </div>
  );
};

const TdpConflictModal: FC<Props> = ({ onTakeAll, closeModal }) => (
  <ModalRoot closeModal={closeModal} bAllowFullSize>
    <FocusRoot>
      <TdpConflictBody onTakeAll={onTakeAll} closeModal={closeModal} />
    </FocusRoot>
  </ModalRoot>
);

/** Open the full-screen first-run TDP take-over modal. */
export function openTdpConflictModal(onTakeAll: () => void): void {
  showModal(<TdpConflictModal onTakeAll={onTakeAll} />, window);
}
