import { FC, useMemo, useState } from "react";
import { ModalRoot, showModal, TextField, Focusable } from "@decky/ui";
import { LuPlus, LuPencil, LuTrash2, LuCheck } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { Loading } from "./Loading";
import { segmentGroupStyle, segmentItemStyle } from "./segmented";
import { useCustomVars } from "../launch/useCustomVars";
import { CustomVarDef } from "../api";
import { validateCustomVar, customVarToken } from "../launch/customVars";
import { baseCatalogTokens } from "../launch/catalog";

const emptyDraft = (id: string): CustomVarDef => ({ id, name: "", kind: "env", envName: "", envValue: "", arg: "" });

const summaryOf = (v: CustomVarDef): string =>
  v.kind === "arg" ? (v.arg ?? "") : `${v.envName ?? ""}=${v.envValue ?? ""}`;

const KindChip: FC<{ active: boolean; label: string; onSelect: () => void }> = ({ active, label, onSelect }) => (
  <Focusable
    onActivate={onSelect}
    onClick={onSelect}
    style={{ ...segmentItemStyle(active), flex: 1, padding: "7px 10px" }}
  >
    {label}
  </Focusable>
);

const Field: FC<{ label: string; value: string; placeholder: string; onChange: (v: string) => void }> = ({ label, value, placeholder, onChange }) => (
  <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
    <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{label}</span>
    <TextField
      value={value}
      onChange={(e) => onChange(e.target.value)}
      // @ts-expect-error Decky TextField forwards input attrs; placeholder is valid.
      placeholder={placeholder}
    />
  </div>
);

const ManagerBody: FC = () => {
  const { t } = useI18n();
  const { vars, save, newId } = useCustomVars();
  const [draft, setDraft] = useState<CustomVarDef>(() => emptyDraft(newId()));

  if (vars === null) return <Loading />;

  const isEdit = vars.some((v) => v.id === draft.id);
  const taken = useMemo(() => {
    const s = baseCatalogTokens();
    for (const v of vars) if (v.id !== draft.id) s.add(customVarToken(v));
    return s;
  }, [vars, draft.id]);
  const err = validateCustomVar(draft, taken);
  const patch = (p: Partial<CustomVarDef>) => setDraft((d) => ({ ...d, ...p }));

  const onSave = () => {
    if (err) return;
    save(isEdit ? vars.map((v) => (v.id === draft.id ? draft : v)) : [...vars, draft]);
    setDraft(emptyDraft(newId()));
  };
  const onDelete = (id: string) => {
    save(vars.filter((v) => v.id !== id));
    if (draft.id === id) setDraft(emptyDraft(newId()));
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.md, padding: theme.space.sm, maxWidth: 640, width: "100%", margin: "0 auto" }}>
      <div>
        <div style={{ fontSize: theme.font.value, color: theme.color.textPrimary }}>{t("customVars.title")}</div>
        <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, lineHeight: 1.4, marginTop: 2 }}>{t("customVars.intro")}</div>
      </div>

      {vars.length === 0 ? (
        <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("customVars.empty")}</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
          {vars.map((v) => (
            <div key={v.id} style={{ ...theme.card, display: "flex", alignItems: "center", gap: theme.space.md, padding: `${theme.space.sm}px ${theme.space.md}px` }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: theme.font.body, fontWeight: 600, color: theme.color.textPrimary, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{v.name}</div>
                <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, fontFamily: "monospace", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{summaryOf(v)}</div>
              </div>
              <Focusable onActivate={() => setDraft({ ...emptyDraft(v.id), ...v })} onClick={() => setDraft({ ...emptyDraft(v.id), ...v })} style={{ padding: 6, cursor: "pointer", flexShrink: 0 }}>
                <LuPencil size={16} color={theme.color.textMuted} />
              </Focusable>
              <Focusable onActivate={() => onDelete(v.id)} onClick={() => onDelete(v.id)} style={{ padding: 6, cursor: "pointer", flexShrink: 0 }}>
                <LuTrash2 size={16} color={theme.color.danger} />
              </Focusable>
            </div>
          ))}
        </div>
      )}

      <div style={{ ...theme.card, display: "flex", flexDirection: "column", gap: theme.space.sm, padding: theme.space.md }}>
        <div style={{ ...theme.sectionLabel }}>{isEdit ? t("customVars.editing") : t("customVars.new")}</div>
        <Field label={t("customVars.name")} value={draft.name} placeholder={t("customVars.name.ph")} onChange={(name) => patch({ name })} />
        <div style={segmentGroupStyle}>
          <KindChip active={draft.kind === "env"} label={t("customVars.kind.env")} onSelect={() => patch({ kind: "env" })} />
          <KindChip active={draft.kind === "arg"} label={t("customVars.kind.arg")} onSelect={() => patch({ kind: "arg" })} />
        </div>
        {draft.kind === "env" ? (
          <>
            <Field label={t("customVars.env.name")} value={draft.envName ?? ""} placeholder="DXVK_FRAME_RATE" onChange={(envName) => patch({ envName })} />
            <Field label={t("customVars.env.value")} value={draft.envValue ?? ""} placeholder="60" onChange={(envValue) => patch({ envValue })} />
          </>
        ) : (
          <Field label={t("customVars.arg.flag")} value={draft.arg ?? ""} placeholder="-nombre" onChange={(arg) => patch({ arg })} />
        )}
        <Focusable
          onActivate={onSave}
          onClick={onSave}
          style={{
            marginTop: 2,
            textAlign: "center",
            padding: "9px 12px",
            borderRadius: theme.radius.sm,
            cursor: err ? "default" : "pointer",
            fontSize: theme.font.body,
            fontWeight: 600,
            color: theme.color.onAccent,
            background: theme.color.accent,
            opacity: err ? 0.4 : 1,
            display: "flex", alignItems: "center", justifyContent: "center", gap: 6,
          }}
        >
          {isEdit ? <LuCheck size={15} /> : <LuPlus size={15} />}
          {isEdit ? t("customVars.save") : t("customVars.add")}
        </Focusable>
        {err && <div style={{ fontSize: theme.font.caption, color: theme.color.warn }}>{t(`customVars.err.${err}`)}</div>}
      </div>
    </div>
  );
};

const CustomVarsModal: FC<{ closeModal?: () => void }> = ({ closeModal }) => (
  <ModalRoot closeModal={closeModal} bAllowFullSize>
    <ManagerBody />
  </ModalRoot>
);

/** Open the "Mis variables" manager. `onClosed` re-syncs the caller. */
export function openCustomVarsManager(onClosed: () => void): void {
  showModal(<CustomVarsModal />, window, { fnOnClose: onClosed });
}
