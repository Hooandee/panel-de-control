import { FC, useEffect, useRef, useState } from "react";
import { ModalRoot, showModal, Focusable, ButtonItem, TextField, DialogButton } from "@decky/ui";
import { LuChevronUp, LuChevronDown, LuEye, LuEyeOff, LuTrash2, LuPlus, LuCheck } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { FocusRoot } from "./FocusRoot";
import { IconAction } from "./IconAction";
import { IconPickerGrid } from "./IconPickerGrid";
import { Loading } from "./Loading";
import { ContainedSlider } from "./ContainedSlider";
import { segmentGroupStyle, segmentItemStyle } from "./segmented";
import { PRESET_ICON_KEYS, presetIconNode } from "../tdp/powerPresetIcons";
import { resolveItems, BuiltinWatts, BUILTIN_LABEL_KEY } from "../tdp/powerPresets";
import {
  PowerPresetState, PowerPresetBoost, BoostMode,
  getPowerPresets, createPowerPreset, updatePowerPreset,
  deletePowerPreset, movePowerPreset, setPowerPresetHidden,
} from "../api";

interface Props {
  builtinWatts: BuiltinWatts;
  onAc: boolean;
  currentWatts: number; // seed for a freshly-added preset
  min: number;
  max: number; // charger ceiling: the real cap for a stored preset
  supportsAdvanced: boolean;
  off2Max: number;
  off3Max: number;
  onClose?: () => void; // refresh the chip row when the manager closes
  closeModal?: () => void;
}

type CustomEntry = PowerPresetState["custom"][string];

const BOOST_MODES: BoostMode[] = ["estable", "auto", "custom"];

/** Alert-style confirm before deleting a preset. */
const DeleteConfirm: FC<{ onConfirm: () => void; closeModal?: () => void }> = ({ onConfirm, closeModal }) => {
  const { t } = useI18n();
  return (
    <ModalRoot onCancel={closeModal} onEscKeypress={closeModal}>
      <FocusRoot style={{ display: "flex", flexDirection: "column", gap: theme.space.md }}>
        <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, fontSize: 20, fontWeight: 700 }}>
          <LuTrash2 size={20} color={theme.color.danger} /> {t("tdp.presets.delete.title")}
        </div>
        <div style={{ fontSize: theme.font.body, color: theme.color.textPrimary, lineHeight: 1.4 }}>
          {t("tdp.presets.delete.desc")}
        </div>
        <div style={{ display: "flex", gap: theme.space.sm }}>
          <DialogButton style={{ flex: 1, minWidth: 0 }} onClick={() => { closeModal?.(); onConfirm(); }}>
            {t("tdp.presets.delete")}
          </DialogButton>
          <DialogButton style={{ flex: 1, minWidth: 0 }} onClick={() => closeModal?.()}>
            {t("tdp.presets.delete.cancel")}
          </DialogButton>
        </div>
      </FocusRoot>
    </ModalRoot>
  );
};

/** Per-preset boost picker (only shown on boost-capable devices). "none" = leave the
 *  boost mode untouched on apply; a mode makes it explicit; custom reveals the margins. */
const BoostEditor: FC<{
  boost: PowerPresetBoost | null;
  off2Max: number;
  off3Max: number;
  onPickMode: (boost: PowerPresetBoost | null) => void;
  onOffsets: (boost: PowerPresetBoost) => void;
}> = ({ boost, off2Max, off3Max, onPickMode, onOffsets }) => {
  const { t } = useI18n();
  const active = boost?.mode ?? "none";
  const off2 = boost?.off2 ?? 0;
  const off3 = boost?.off3 ?? 0;
  return (
    <div style={{ marginTop: theme.space.xs }}>
      <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("tdp.boost.title")}</span>
      <div style={{ ...segmentGroupStyle, marginTop: theme.space.xs }}>
        <Focusable
          style={{ ...segmentItemStyle(active === "none"), flex: 1, padding: "4px 6px" }}
          onActivate={() => onPickMode(null)}
          onClick={() => onPickMode(null)}
        >
          {t("tdp.presets.boost.none")}
        </Focusable>
        {BOOST_MODES.map((m) => (
          <Focusable
            key={m}
            style={{ ...segmentItemStyle(active === m), flex: 1, padding: "4px 6px" }}
            onActivate={() => onPickMode({ mode: m, off2: m === "custom" ? off2 : 0, off3: m === "custom" ? off3 : 0 })}
            onClick={() => onPickMode({ mode: m, off2: m === "custom" ? off2 : 0, off3: m === "custom" ? off3 : 0 })}
          >
            {t(`tdp.boost.mode.${m}`)}
          </Focusable>
        ))}
      </div>
      {active === "custom" && (
        <>
          <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, marginTop: theme.space.xs }}>
            {t("tdp.level.slow")} · +{off2} W
          </div>
          <ContainedSlider value={off2} min={0} max={off2Max} step={1} onChange={(v) => onOffsets({ mode: "custom", off2: v, off3 })} />
          <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
            {t("tdp.level.fast")} · +{off3} W
          </div>
          <ContainedSlider value={off3} min={0} max={off3Max} step={1} onChange={(v) => onOffsets({ mode: "custom", off2, off3: v })} />
        </>
      )}
    </div>
  );
};

const Body: FC<Props> = ({ builtinWatts, onAc, currentWatts, min, max, supportsAdvanced, off2Max, off3Max, closeModal }) => {
  const { t } = useI18n();
  const [state, setState] = useState<PowerPresetState | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const alive = useRef(true);
  const editTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    getPowerPresets().then((s) => alive.current && setState(s)).catch(() => {});
    return () => {
      alive.current = false;
      if (editTimer.current) clearTimeout(editTimer.current);
    };
  }, []);

  if (!state) return <Loading />;

  // The manager doesn't use the active flag, so a neutral live boost is fine here.
  const items = resolveItems(state, builtinWatts, onAc, currentWatts, max, { mode: "estable", off2: 0, off3: 0 }).manager;
  const wrap = (p: Promise<PowerPresetState>) => p.then((s) => alive.current && setState(s)).catch(() => {});
  const patch = (id: string, entry: CustomEntry) =>
    setState((cur) => (cur ? { ...cur, custom: { ...cur.custom, [id]: entry } } : cur));
  // Optimistic local + debounced commit for dragged/typed values; immediate for discrete taps.
  const commitDebounced = (id: string, entry: CustomEntry) => {
    patch(id, entry);
    if (editTimer.current) clearTimeout(editTimer.current);
    editTimer.current = setTimeout(() => wrap(updatePowerPreset(id, entry.watts, entry.icon, entry.boost, entry.name)), 200);
  };
  const commitNow = (id: string, entry: CustomEntry) => {
    if (editTimer.current) clearTimeout(editTimer.current);
    patch(id, entry);
    wrap(updatePowerPreset(id, entry.watts, entry.icon, entry.boost, entry.name));
  };
  const confirmDelete = (id: string) =>
    showModal(<DeleteConfirm onConfirm={() => wrap(deletePowerPreset(id))} />);

  const rowTitle = (it: (typeof items)[number]) =>
    it.kind === "builtin" ? t(BUILTIN_LABEL_KEY[it.id]) : it.name || it.label;
  const rowSub = (it: (typeof items)[number]) => (it.kind === "builtin" || it.name ? it.label : "");

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
                {rowTitle(it)}
                {rowSub(it) && <span style={{ color: theme.color.textMuted }}> · {rowSub(it)}</span>}
              </span>
              <IconAction label={t("customize.moveUp")} color={i === 0 ? theme.color.textMuted : theme.color.accent} disabled={i === 0} onTap={() => wrap(movePowerPreset(it.id, -1))}><LuChevronUp size={18} /></IconAction>
              <IconAction label={t("customize.moveDown")} color={i === items.length - 1 ? theme.color.textMuted : theme.color.accent} disabled={i === items.length - 1} onTap={() => wrap(movePowerPreset(it.id, 1))}><LuChevronDown size={18} /></IconAction>
              <IconAction label={t("customize.hide")} color={theme.color.textMuted} onTap={() => wrap(setPowerPresetHidden(it.id, !it.hidden))}>{it.hidden ? <LuEyeOff size={18} /> : <LuEye size={18} />}</IconAction>
              {it.deletable && (
                <IconAction label={t("tdp.presets.delete")} color={theme.color.danger} onTap={() => confirmDelete(it.id)}>
                  <LuTrash2 size={18} />
                </IconAction>
              )}
            </div>
            {it.editable && editing === it.id && (
              <div style={{ paddingLeft: theme.space.lg, display: "flex", flexDirection: "column", gap: theme.space.xs }}>
                <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("tdp.presets.name")}</span>
                <TextField value={it.name} bShowClearAction onChange={(e) => commitDebounced(it.id, { watts: it.watts, icon: it.icon, name: e.target.value, boost: it.boost })} />
                <ContainedSlider value={it.watts} min={min} max={max} step={1} showValue onChange={(w) => commitDebounced(it.id, { watts: w, icon: it.icon, name: it.name, boost: it.boost })} />
                <IconPickerGrid keys={PRESET_ICON_KEYS} value={it.icon} renderIcon={presetIconNode} onPick={(k) => commitNow(it.id, { watts: it.watts, icon: k, name: it.name, boost: it.boost })} />
                {supportsAdvanced && (
                  <BoostEditor
                    boost={it.boost}
                    off2Max={off2Max}
                    off3Max={off3Max}
                    onPickMode={(b) => commitNow(it.id, { watts: it.watts, icon: it.icon, name: it.name, boost: b })}
                    onOffsets={(b) => commitDebounced(it.id, { watts: it.watts, icon: it.icon, name: it.name, boost: b })}
                  />
                )}
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

      <ButtonItem layout="below" onClick={() => wrap(createPowerPreset(Math.round(currentWatts), "bolt", null, ""))}>
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
