import { FC, ReactNode } from "react";
import { DialogButton, ModalRoot } from "@decky/ui";

import { theme } from "../theme";
import { FocusRoot } from "./FocusRoot";

interface Props {
  title: string;
  desc: string;
  confirmLabel: string;
  cancelLabel: string;
  onConfirm: () => void;
  icon?: ReactNode; // optional leading icon in the title row
  closeModal?: () => void;
}

/** Compact confirm/cancel alert. Shown via showModal; confirm runs onConfirm then closes. */
export const ConfirmDialog: FC<Props> = ({ title, desc, confirmLabel, cancelLabel, onConfirm, icon, closeModal }) => (
  <ModalRoot onCancel={closeModal} onEscKeypress={closeModal}>
    <FocusRoot style={{ display: "flex", flexDirection: "column", gap: theme.space.md }}>
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, fontSize: 20, fontWeight: 700 }}>
        {icon}
        {title}
      </div>
      <div style={{ fontSize: theme.font.body, color: theme.color.textPrimary, lineHeight: 1.4 }}>{desc}</div>
      <div style={{ display: "flex", gap: theme.space.sm }}>
        <DialogButton style={{ flex: 1, minWidth: 0 }} onClick={() => { closeModal?.(); onConfirm(); }}>
          {confirmLabel}
        </DialogButton>
        <DialogButton style={{ flex: 1, minWidth: 0 }} onClick={() => closeModal?.()}>
          {cancelLabel}
        </DialogButton>
      </div>
    </FocusRoot>
  </ModalRoot>
);
