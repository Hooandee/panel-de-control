import { FC, useState } from "react";
import { DialogButton, ModalRoot, TextField, showModal } from "@decky/ui";

import { useI18n } from "../i18n";
import { theme } from "../theme";

const SaveProfileBody: FC<{ initial: string; onSave: (name: string) => void; closeModal?: () => void }> = ({
  initial,
  onSave,
  closeModal,
}) => {
  const { t } = useI18n();
  const [name, setName] = useState(initial);
  const save = () => {
    const trimmed = name.trim();
    if (trimmed) onSave(trimmed);
    closeModal?.();
  };
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.md, padding: theme.space.sm }}>
      <div style={{ fontSize: theme.font.value, color: theme.color.textPrimary }}>
        {t("audio.profile.saveTitle")}
      </div>
      <TextField value={name} onChange={(e) => setName(e.target.value)} />
      <DialogButton onClick={save} disabled={!name.trim()}>
        {t("audio.profile.save")}
      </DialogButton>
    </div>
  );
};

const SaveProfileModal: FC<{ initial: string; onSave: (name: string) => void; closeModal?: () => void }> = ({
  initial,
  onSave,
  closeModal,
}) => (
  <ModalRoot closeModal={closeModal}>
    <SaveProfileBody initial={initial} onSave={onSave} closeModal={closeModal} />
  </ModalRoot>
);

/** Prompt for a profile name (on-screen keyboard) then save. `initial` pre-fills it. */
export function openSaveProfileModal(initial: string, onSave: (name: string) => void): void {
  showModal(<SaveProfileModal initial={initial} onSave={onSave} />, window);
}
