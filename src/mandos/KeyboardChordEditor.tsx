import { FC, useState } from "react";
import { DialogButton, Dropdown, Focusable, ModalRoot, showModal } from "@decky/ui";
import { LuKeyboard, LuPlus, LuX } from "react-icons/lu";

import { FocusRoot } from "../components/FocusRoot";
import { useI18n } from "../i18n";
import { theme } from "../theme";
import { prettyKey } from "./logic";

const MAX_CHORD_KEYS = 4;

export function addChordKey(keys: string[], key: string): string[] {
  if (!key || keys.includes(key) || keys.length >= MAX_CHORD_KEYS) return keys;
  return [...keys, key];
}

interface KeyboardChordEditorProps {
  initialKeys: string[];
  keyTargets: string[];
  onSave: (keys: string[]) => void;
  closeModal?: () => void;
}

export const KeyboardChordEditorBody: FC<KeyboardChordEditorProps> = ({
  initialKeys,
  keyTargets,
  onSave,
  closeModal,
}) => {
  const { t } = useI18n();
  const [keys, setKeys] = useState(() => [...new Set(initialKeys)].slice(0, MAX_CHORD_KEYS));
  const available = keyTargets.filter((key) => !keys.includes(key));
  const [candidate, setCandidate] = useState(() => keyTargets.find((key) => !initialKeys.includes(key)) ?? "");
  const selectedCandidate = available.includes(candidate) ? candidate : (available[0] ?? "");

  const add = () => {
    const next = addChordKey(keys, selectedCandidate);
    setKeys(next);
    setCandidate(keyTargets.find((key) => !next.includes(key)) ?? "");
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.md, maxWidth: 440, margin: "0 auto", padding: theme.space.lg }}>
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.sm }}>
        <div style={{ width: 44, height: 44, flex: "0 0 auto", display: "grid", placeItems: "center", borderRadius: theme.radius.md, background: theme.color.surfaceRaised, boxShadow: `inset 0 0 0 1px ${theme.color.hairline}` }}>
          <LuKeyboard size={22} color={theme.color.accent} />
        </div>
        <div>
          <div style={{ fontSize: theme.font.value, fontWeight: 700, color: theme.color.textPrimary }}>
            {t("mandos.shortcut.title")}
          </div>
          <div style={{ marginTop: 2, fontSize: theme.font.caption, lineHeight: 1.35, color: theme.color.textMuted }}>
            {t("mandos.shortcut.desc")}
          </div>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
        <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
          {t("mandos.shortcut.selected")}
        </span>
        {keys.length === 0 ? (
          <div style={{ padding: theme.space.md, borderRadius: theme.radius.sm, textAlign: "center", fontSize: theme.font.caption, color: theme.color.textMuted, boxShadow: `inset 0 0 0 1px ${theme.color.hairline}` }}>
            {t("mandos.shortcut.empty")}
          </div>
        ) : (
          <div style={{ display: "flex", flexWrap: "wrap", gap: theme.space.xs }}>
            {keys.map((key) => (
              <DialogButton
                key={key}
                aria-label={`${t("mandos.shortcut.remove")} ${prettyKey(key)}`}
                style={{ width: "auto", minWidth: 0, display: "flex", alignItems: "center", gap: theme.space.xs, padding: `6px ${theme.space.sm}px` }}
                onClick={() => setKeys((current) => current.filter((item) => item !== key))}
              >
                {prettyKey(key)} <LuX size={13} />
              </DialogButton>
            ))}
          </div>
        )}
      </div>

      <div style={{ display: "flex", alignItems: "end", gap: theme.space.sm }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ marginBottom: theme.space.xs, fontSize: theme.font.caption, color: theme.color.textMuted }}>
            {t("mandos.shortcut.key")}
          </div>
          <Dropdown
            rgOptions={available.map((key) => ({ data: key, label: prettyKey(key) }))}
            selectedOption={selectedCandidate || undefined}
            strDefaultLabel={t("mandos.shortcut.noMore")}
            onChange={(option) => setCandidate(option.data as string)}
          />
        </div>
        <DialogButton
          aria-label={t("mandos.shortcut.add")}
          disabled={!selectedCandidate || keys.length >= MAX_CHORD_KEYS}
          style={{ width: "auto", minWidth: 48, display: "grid", placeItems: "center" }}
          onClick={add}
        >
          <LuPlus size={17} />
        </DialogButton>
      </div>

      <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
        {t("mandos.shortcut.limit")}
      </div>

      <Focusable style={{ display: "flex", gap: theme.space.sm }}>
        <DialogButton
          disabled={keys.length === 0}
          style={{ flex: 1, minWidth: 0 }}
          onClick={() => { onSave(keys); closeModal?.(); }}
        >
          {t("mandos.shortcut.save")}
        </DialogButton>
        <DialogButton style={{ flex: 1, minWidth: 0 }} onClick={() => closeModal?.()}>
          {t("mandos.shortcut.cancel")}
        </DialogButton>
      </Focusable>
    </div>
  );
};

const KeyboardChordEditorRoot: FC<KeyboardChordEditorProps> = (props) => (
  <ModalRoot closeModal={props.closeModal} bAllowFullSize>
    <FocusRoot>
      <KeyboardChordEditorBody {...props} />
    </FocusRoot>
  </ModalRoot>
);

export function openKeyboardChordEditor(
  options: Omit<KeyboardChordEditorProps, "closeModal">,
): void {
  showModal(<KeyboardChordEditorRoot {...options} />, window);
}
