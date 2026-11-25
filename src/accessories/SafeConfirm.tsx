import { DialogButton, Focusable, ModalRoot } from "@decky/ui";
import { FC } from "react";

import { FocusRoot } from "../components/FocusRoot";
import { showModal } from "../navigation/showModal";
import { theme } from "../theme";

interface Props {
  title: string;
  desc: string;
  confirmLabel: string;
  cancelLabel: string;
  onConfirm: () => void;
  closeModal?: () => void;
}

/** Destructive confirmation that opens with the safe choice focused. */
const SafeConfirm: FC<Props> = ({ title, desc, confirmLabel, cancelLabel, onConfirm, closeModal }) => (
  <ModalRoot onCancel={closeModal} onEscKeypress={closeModal}>
    <FocusRoot style={{ display: "flex", flexDirection: "column", gap: theme.space.md }}>
      <div style={{ fontSize: 20, fontWeight: 700 }}>{title}</div>
      <div style={{ fontSize: theme.font.body, color: theme.color.textPrimary, lineHeight: 1.4 }}>{desc}</div>
      <Focusable flow-children="row" style={{ display: "flex", gap: theme.space.sm }}>
        <DialogButton style={{ flex: 1, minWidth: 0 }} onClick={() => closeModal?.()}>{cancelLabel}</DialogButton>
        <DialogButton style={{ flex: 1, minWidth: 0, color: theme.color.danger }} onClick={() => { closeModal?.(); onConfirm(); }}>
          {confirmLabel}
        </DialogButton>
      </Focusable>
    </FocusRoot>
  </ModalRoot>
);

/** `parent` is the window the caller lives in: a confirmation asked from an editor must open
 *  over that editor in Steam's main window, not in the quick access menu it closed. */
export function confirmDestructive(props: Omit<Props, "closeModal">, parent: Window = window, onDismiss?: () => void): void {
  showModal(<SafeConfirm {...props} />, parent, { fnOnClose: onDismiss });
}
