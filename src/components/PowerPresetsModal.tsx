import { FC, useEffect, useRef, useState } from "react";
import { ModalRoot, showModal, Focusable, ButtonItem, TextField } from "@decky/ui";
import { LuChevronUp, LuChevronDown, LuEye, LuEyeOff, LuTrash2, LuPlus, LuCheck } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { FocusRoot } from "./FocusRoot";
import { ConfirmDialog } from "./ConfirmDialog";
import { IconAction } from "./IconAction";
import { IconPickerGrid } from "./IconPickerGrid";
import { Loading } from "./Loading";
import { ContainedSlider } from "./ContainedSlider";
import { segmentGroupStyle, segmentItemStyle } from "./segmented";
import { PRESET_ICON_KEYS, presetIconNode } from "../tdp/powerPresetIcons";
import { resolveItems, BuiltinWatts, PresetItem, presetTitle, presetSub } from "../tdp/powerPresets";
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
  pl2Max: number; // firmware SPPT rail ceiling
  pl3Max: number; // firmware FPPT rail ceiling
  onClose?: () => void; // refresh the chip row when the manager closes
  closeModal?: () => void;
}

type CustomEntry = PowerPresetState["custom"][string];

const CAP = 30; // mirrors PowerPresetStore._MAX_CUSTOM — hide "Add" once reached
const BOOST_MODES: BoostMode[] = ["estable", "auto", "custom"];

/** Per-preset boost picker (only shown on boost-capable devices). A custom preset always
 *  carries a definite boost: "Sin boost" = estable (flat, no headroom), auto, or custom
 *  (reveals the margins). Only built-ins leave the live boost untouched. */
const BoostEditor: FC<{
  boost: PowerPresetBoost | null;
  watts: number; // the preset's PL1 — the base the margins stack on
  pl2Max: number;
  pl3Max: number;
  onPickMode: (boost: PowerPresetBoost) => void;
  onOffsets: (boost: PowerPresetBoost) => void;
}> = ({ boost, watts, pl2Max, pl3Max, onPickMode, onOffsets }) => {
  const { t } = useI18n();
  const active = boost?.mode ?? "estable";
  // Bound each margin so the resulting rail can't exceed its firmware max: SPPT = PL1+off2
  // ≤ pl2Max, FPPT = SPPT+off3 ≤ pl3Max. Same rule as the advanced boost editor — never
  // offer a rail the hardware won't hold.
  const off2Max = Math.max(1, pl2Max - watts);
  const off2 = Math.min(boost?.off2 ?? 0, off2Max);
  const off3Max = Math.max(1, pl3Max - (watts + off2));
  const off3 = Math.min(boost?.off3 ?? 0, off3Max);
  // "Sin boost" IS estable (flat, no headroom over PL1) — that's what "no boost" means.
  const label = (m: BoostMode) => (m === "estable" ? t("tdp.presets.boost.none") : t(`tdp.boost.mode.${m}`));
  return (
    <div style={{ marginTop: theme.space.xs }}>
      <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("tdp.boost.title")}</span>
      <div style={{ ...segmentGroupStyle, marginTop: theme.space.xs }}>
        {BOOST_MODES.map((m) => (
          <Focusable
            key={m}
            style={{ ...segmentItemStyle(active === m), flex: 1, padding: "4px 6px" }}
            onActivate={() => onPickMode({ mode: m, off2: m === "custom" ? off2 : 0, off3: m === "custom" ? off3 : 0 })}
            onClick={() => onPickMode({ mode: m, off2: m === "custom" ? off2 : 0, off3: m === "custom" ? off3 : 0 })}
          >
            {label(m)}
          </Focusable>
        ))}
      </div>
      {active === "custom" && (
        <>
          <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, marginTop: theme.space.xs }}>
            {t("tdp.level.slow")} · +{off2} W → {watts + off2} W
          </div>
          <ContainedSlider
            value={off2}
            min={0}
            max={off2Max}
            step={1}
            onChange={(v) => onOffsets({ mode: "custom", off2: v, off3: Math.min(off3, Math.max(0, pl3Max - (watts + v))) })}
          />
          <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
            {t("tdp.level.fast")} · +{off3} W → {watts + off2 + off3} W
          </div>
          <ContainedSlider value={off3} min={0} max={off3Max} step={1} onChange={(v) => onOffsets({ mode: "custom", off2, off3: v })} />
        </>
      )}
    </div>
  );
};

const Body: FC<Props> = ({ builtinWatts, onAc, currentWatts, min, max, supportsAdvanced, pl2Max, pl3Max, onClose, closeModal }) => {
  const { t } = useI18n();
  const [state, setState] = useState<PowerPresetState | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  // Local edit buffer for the open row: inputs render from this, not the server snapshot,
  // so an in-flight debounced echo can't snap a slider/text field back mid-edit.
  const [draft, setDraft] = useState<CustomEntry | null>(null);
  const alive = useRef(true);
  const editTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingSave = useRef<{ id: string; entry: CustomEntry } | null>(null);

  const flushSave = () => {
    if (editTimer.current) {
      clearTimeout(editTimer.current);
      editTimer.current = null;
    }
    const p = pendingSave.current;
    pendingSave.current = null;
    if (p) wrap(updatePowerPreset(p.id, p.entry.watts, p.entry.icon, p.entry.boost, p.entry.name));
  };

  useEffect(() => {
    getPowerPresets().then((s) => alive.current && setState(s)).catch(() => {});
    return () => {
      alive.current = false;
      if (editTimer.current) clearTimeout(editTimer.current);
      // On close: persist a still-pending edit, THEN refresh the chip row — so the parent
      // never reads a pre-save snapshot. If nothing is pending, refresh right away.
      const p = pendingSave.current;
      if (p) {
        updatePowerPreset(p.id, p.entry.watts, p.entry.icon, p.entry.boost, p.entry.name)
          .catch(() => {})
          .then(() => onClose?.());
      } else {
        onClose?.();
      }
    };
  }, []);

  if (!state) return <Loading />;

  // The manager doesn't use the active flag, so a neutral live boost is fine here.
  const items = resolveItems(state, builtinWatts, onAc, currentWatts, max, { mode: "estable", off2: 0, off3: 0 }).manager;
  const customCount = items.filter((it) => it.kind === "custom").length;
  const wrap = (p: Promise<PowerPresetState>) => p.then((s) => alive.current && setState(s)).catch(() => {});
  const patch = (id: string, entry: CustomEntry) =>
    setState((cur) => (cur ? { ...cur, custom: { ...cur.custom, [id]: entry } } : cur));
  // Dragged/typed values: update the draft, optimistically patch the list, debounce the save.
  const commitDebounced = (id: string, entry: CustomEntry) => {
    setDraft(entry);
    patch(id, entry);
    pendingSave.current = { id, entry };
    if (editTimer.current) clearTimeout(editTimer.current);
    editTimer.current = setTimeout(() => {
      editTimer.current = null;
      pendingSave.current = null;
      wrap(updatePowerPreset(id, entry.watts, entry.icon, entry.boost, entry.name));
    }, 200);
  };
  // Discrete taps (icon / boost mode): save immediately.
  const commitNow = (id: string, entry: CustomEntry) => {
    if (editTimer.current) clearTimeout(editTimer.current);
    editTimer.current = null;
    pendingSave.current = null;
    setDraft(entry);
    patch(id, entry);
    wrap(updatePowerPreset(id, entry.watts, entry.icon, entry.boost, entry.name));
  };
  const confirmDelete = (id: string) =>
    showModal(
      <ConfirmDialog
        title={t("tdp.presets.delete.title")}
        desc={t("tdp.presets.delete.desc")}
        confirmLabel={t("tdp.presets.delete")}
        cancelLabel={t("tdp.presets.delete.cancel")}
        icon={<LuTrash2 size={20} color={theme.color.danger} />}
        onConfirm={() => wrap(deletePowerPreset(id))}
      />,
      window,
    );
  // The editable fields of a preset, for building a commit payload with one field changed.
  const entryOf = (it: PresetItem): CustomEntry => ({ watts: it.watts, icon: it.icon, name: it.name, boost: it.boost });
  // Open/close the editor for a row, flushing any pending save so switching rows never drops it.
  const toggleEdit = (it: PresetItem) => {
    flushSave();
    if (editing === it.id) {
      setEditing(null);
      setDraft(null);
    } else {
      setEditing(it.id);
      setDraft(entryOf(it));
    }
  };
  const onDone = () => {
    // Just dismiss — unmount cleanup flushes the pending save and then refreshes the parent.
    closeModal?.();
  };

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
          onActivate={onDone}
          onClick={onDone}
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
                {presetTitle(it, t)}
                {presetSub(it) && <span style={{ color: theme.color.textMuted }}> · {presetSub(it)}</span>}
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
            {it.editable && editing === it.id && (() => {
              const d = draft ?? entryOf(it);
              return (
                <div style={{ paddingLeft: theme.space.lg, display: "flex", flexDirection: "column", gap: theme.space.xs }}>
                  <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("tdp.presets.name")}</span>
                  <TextField value={d.name} bShowClearAction onChange={(e) => commitDebounced(it.id, { ...d, name: e.target.value })} />
                  <ContainedSlider value={d.watts} min={min} max={max} step={1} showValue onChange={(w) => commitDebounced(it.id, { ...d, watts: w })} />
                  <IconPickerGrid keys={PRESET_ICON_KEYS} value={d.icon} renderIcon={presetIconNode} onPick={(k) => commitNow(it.id, { ...d, icon: k })} />
                  {supportsAdvanced && (
                    <BoostEditor
                      boost={d.boost}
                      watts={d.watts}
                      pl2Max={pl2Max}
                      pl3Max={pl3Max}
                      onPickMode={(b) => commitNow(it.id, { ...d, boost: b })}
                      onOffsets={(b) => commitDebounced(it.id, { ...d, boost: b })}
                    />
                  )}
                </div>
              );
            })()}
            {it.editable && (
              <Focusable
                style={{ paddingLeft: theme.space.lg, fontSize: theme.font.caption, color: theme.color.textMuted, cursor: "pointer" }}
                onActivate={() => toggleEdit(it)}
                onClick={() => toggleEdit(it)}
              >
                {editing === it.id ? t("tdp.presets.doneEdit") : t("tdp.presets.edit")}
              </Focusable>
            )}
          </div>
        ))}
      </div>

      {customCount < CAP && (
        <ButtonItem layout="below" onClick={() => wrap(createPowerPreset(Math.round(currentWatts), "bolt", null, ""))}>
          <span style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: theme.space.xs }}>
            <LuPlus size={16} /> {t("tdp.presets.add")}
          </span>
        </ButtonItem>
      )}
    </div>
  );
};

const PowerPresetsModal: FC<Props> = (props) => (
  // Dismiss on every path (Done / B / esc) goes through the raw closeModal → Body's unmount
  // cleanup flushes any pending save and then calls onClose to refresh the parent, in order.
  <ModalRoot closeModal={props.closeModal} bAllowFullSize>
    <FocusRoot>
      <Body {...props} />
    </FocusRoot>
  </ModalRoot>
);

export function openPowerPresetsModal(props: Omit<Props, "closeModal">): void {
  showModal(<PowerPresetsModal {...props} />, window);
}
