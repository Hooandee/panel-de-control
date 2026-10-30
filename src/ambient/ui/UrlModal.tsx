import { ModalRoot, TextField, showModal } from "@decky/ui";
import { useState, type FC } from "react";

import { translate, useI18n } from "../../i18n";
import { theme } from "../../theme";
import { Button } from "./primitives";

const Body: FC<{ title: string; onSave: (url: string, name: string) => Promise<boolean>; closeModal?: () => void }> = ({ title, onSave, closeModal }) => {
  const { t } = useI18n();
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const save = async () => {
    const trimmed = url.trim();
    if (!/^https?:\/\/\S+$/i.test(trimmed)) {
      setError(t("ambient.add.url.invalid"));
      return;
    }
    if (await onSave(trimmed, name.trim() || trimmed)) closeModal?.();
    else setError(t("ambient.add.url.invalid"));
  };
  return (
    <ModalRoot closeModal={closeModal}>
      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.md }}>
        <div style={{ fontSize: 16, fontWeight: 600 }}>{title}</div>
        <TextField label={t("ambient.add.url.field")} value={url} onChange={(e) => { setUrl(e.target.value); setError(null); }} />
        <TextField label={t("ambient.add.url.name")} value={name} onChange={(e) => setName(e.target.value)} />
        {error && <div style={{ fontSize: theme.font.caption, color: theme.color.warn }}>{error}</div>}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: theme.space.sm }}>
          <Button label={t("ambient.add.cancel")} onActivate={() => closeModal?.()} />
          <Button primary label={t("ambient.add.save")} onActivate={() => void save()} />
        </div>
      </div>
    </ModalRoot>
  );
};

export function openUrlModal(titleKey: string, onSave: (url: string, name: string) => Promise<boolean>): void {
  showModal(<Body title={translate(titleKey)} onSave={onSave} />, window);
}
