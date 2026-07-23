import { FC, useEffect, useState } from "react";
import { ModalRoot, showModal, Focusable, ButtonItem } from "@decky/ui";
import { LuChevronUp, LuChevronDown, LuEye, LuEyeOff, LuTrash2, LuPlus, LuCheck } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { FocusRoot } from "./FocusRoot";
import { IconAction } from "./IconAction";
import { IconPickerGrid } from "./IconPickerGrid";
import { Loading } from "./Loading";
import { ContainedSlider } from "./ContainedSlider";
import { PRESET_ICON_KEYS, presetIconNode } from "../tdp/powerPresetIcons";
import { resolveItems, BuiltinWatts } from "../tdp/powerPresets";
import {
  PowerPresetState, getPowerPresets, createPowerPreset, updatePowerPreset,
  deletePowerPreset, movePowerPreset, setPowerPresetHidden,
} from "../api";

interface Props {
  builtinWatts: BuiltinWatts;
  onAc: boolean;
  currentWatts: number; // seed for a freshly-added preset
  min: number;
  max: number;
  onClose?: () => void; // refresh the chip row when the manager closes
  closeModal?: () => void;
}

const BUILTIN_LABEL_KEY: Record<string, string> = {
  quiet: "tdp.preset.save",
  balanced: "tdp.preset.balanced",
  turbo: "tdp.preset.turbo",
};

const Body: FC<Props> = ({ builtinWatts, onAc, currentWatts, min, max, closeModal }) => {
  const { t } = useI18n();
  const [state, setState] = useState<PowerPresetState | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [confirmDel, setConfirmDel] = useState<string | null>(null);

  useEffect(() => {
    getPowerPresets().then(setState).catch(() => setState(null));
  }, []);
  if (!state) return <Loading />;

  const items = resolveItems(state, builtinWatts, onAc, currentWatts).manager;
  const wrap = (p: Promise<PowerPresetState>) => p.then(setState).catch(() => {});

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.md, padding: theme.space.sm, maxWidth: 640, width: "100%", margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ fontSize: theme.font.value, color: theme.color.textPrimary }}>{t("tdp.presets.manage.title")}</div>
        <Focusable
          style={{
            display: "flex", alignItems: "center", gap: theme.space.xs,
            padding: `${theme.space.xs}px ${theme.space.md}px`, borderRadius: theme.radius.sm,
            background: theme.color.accent, color: theme.color.onAccent, fontWeight: 700, cursor: "pointer",
          }}
          onActivate={() => closeModal?.()}
          onClick={() => closeModal?.()}
        >
          <LuCheck size={16} /> {t("customize.views.done")}
        </Focusable>
      </div>

      <div style={{ ...theme.card, padding: theme.space.md, display: "flex", flexDirection: "column", gap: theme.space.sm }}>
        {items.map((it, i) => (
          <div key={it.id} style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
            <div style={{ display: "flex", alignItems: "center", gap: theme.space.sm }}>
              <span style={{ display: "flex", color: it.hidden ? theme.color.textMuted : theme.color.accent }}>{presetIconNode(it.icon, 16)}</span>
              <span style={{ flex: 1, minWidth: 0, fontSize: theme.font.body, color: theme.color.textPrimary, opacity: it.hidden ? 0.5 : 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {it.label}
                {it.kind === "builtin" && <span style={{ color: theme.color.textMuted }}> · {t(BUILTIN_LABEL_KEY[it.id])}</span>}
              </span>
              <IconAction label={t("customize.moveUp")} color={i === 0 ? theme.color.textMuted : theme.color.accent} disabled={i === 0} onTap={() => wrap(movePowerPreset(it.id, -1))}><LuChevronUp size={18} /></IconAction>
              <IconAction label={t("customize.moveDown")} color={i === items.length - 1 ? theme.color.textMuted : theme.color.accent} disabled={i === items.length - 1} onTap={() => wrap(movePowerPreset(it.id, 1))}><LuChevronDown size={18} /></IconAction>
              <IconAction label={t("customize.hide")} color={theme.color.textMuted} onTap={() => wrap(setPowerPresetHidden(it.id, !it.hidden))}>{it.hidden ? <LuEyeOff size={18} /> : <LuEye size={18} />}</IconAction>
              {it.deletable && (
                <IconAction label={t("tdp.presets.delete")} color={theme.color.danger}
                  onTap={() => (confirmDel === it.id ? wrap(deletePowerPreset(it.id)) : setConfirmDel(it.id))}>
                  <LuTrash2 size={18} />
                </IconAction>
              )}
            </div>
            {it.editable && editing === it.id && (
              <div style={{ paddingLeft: theme.space.lg, display: "flex", flexDirection: "column", gap: theme.space.xs }}>
                <ContainedSlider value={it.watts} min={min} max={max} step={1} showValue onChange={(w) => wrap(updatePowerPreset(it.id, w, it.icon, it.boost))} />
                <IconPickerGrid keys={PRESET_ICON_KEYS} value={it.icon} renderIcon={presetIconNode} onPick={(k) => wrap(updatePowerPreset(it.id, it.watts, k, it.boost))} />
              </div>
            )}
            {it.editable && (
              <Focusable
                style={{ paddingLeft: theme.space.lg, fontSize: theme.font.caption, color: theme.color.textMuted, cursor: "pointer" }}
                onActivate={() => setEditing(editing === it.id ? null : it.id)}
                onClick={() => setEditing(editing === it.id ? null : it.id)}
              >
                {editing === it.id ? t("tdp.presets.doneEdit") : t("tdp.presets.edit")}
              </Focusable>
            )}
          </div>
        ))}
      </div>

      <ButtonItem layout="below" onClick={() => wrap(createPowerPreset(Math.round(currentWatts), "bolt", null))}>
        <span style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: theme.space.xs }}>
          <LuPlus size={16} /> {t("tdp.presets.add")}
        </span>
      </ButtonItem>
    </div>
  );
};

const PowerPresetsModal: FC<Props> = (props) => {
  const close = () => {
    props.onClose?.();
    props.closeModal?.();
  };
  return (
    <ModalRoot closeModal={close} bAllowFullSize>
      <FocusRoot>
        <Body {...props} closeModal={close} />
      </FocusRoot>
    </ModalRoot>
  );
};

export function openPowerPresetsModal(props: Omit<Props, "closeModal">): void {
  showModal(<PowerPresetsModal {...props} />, window);
}
