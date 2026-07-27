import { FC, ReactNode, useState } from "react";
import { PanelSectionRow, ToggleField, TextField, Spinner, showModal } from "@decky/ui";
import {
  LuArrowUpLeft, LuArrowUpRight, LuArrowDownLeft, LuArrowDownRight,
  LuChevronUp, LuChevronDown, LuChevronRight, LuX, LuRotateCcw, LuRefreshCw,
  LuType, LuMinus, LuPlus, LuMoveVertical, LuCheck, LuPalette, LuSlidersHorizontal,
  LuSettings2, LuTriangleAlert,
} from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { useHud } from "../mangohud/useHud";
import { HudPreview } from "../components/HudPreview";
import { HudDisclosure } from "../components/HudDisclosure";
import { HudSliderRow } from "../components/HudSliderRow";
import { QamAction } from "../components/QamAction";
import { ColorPicker } from "../components/ColorPicker";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { segmentGroupStyle, segmentItemStyle } from "../components/segmented";
import { hasLocalEditor } from "../mangohud/editorUi";
import {
  BLOCK_GROUPS, BlockGroup, COLOR_KEYS, ColorKey, GROUPS, HudItem, HudLayout, HudModel,
  HudPosition, ListRow, MetricId, SPACER_SIZES, TempUnit, PRESETS,
  addMetricItem, addSeparator, addSpacer, addTextItem, blockMetricIds, canLabel, hasBlock, hasMetric,
  listRows, moveRow, removeRow, setMetricLabel, setSpacerSizeAt, setTextAt, toggleMetricItem,
} from "../mangohud/model";

const card = { ...theme.card, minWidth: 0, padding: theme.space.md, overflow: "hidden" } as const;

const POSITIONS: { id: HudPosition; Icon: typeof LuArrowUpLeft }[] = [
  { id: "top-left", Icon: LuArrowUpLeft }, { id: "top-right", Icon: LuArrowUpRight },
  { id: "bottom-left", Icon: LuArrowDownLeft }, { id: "bottom-right", Icon: LuArrowDownRight },
];
const LAYOUTS: HudLayout[] = ["vertical", "horizontal"];
const TEMP_UNITS: TempUnit[] = ["c", "f"];

type AddEntry = { kind: "metric"; id: MetricId } | { kind: "block"; group: BlockGroup };

const rowKey = (r: ListRow): string =>
  r.kind === "block" ? `b:${r.group}`
    : r.kind === "text" ? `t:${r.id}`
    : r.kind === "separator" ? `s:${r.id}`
    : r.kind === "spacer" ? `sp:${r.id}`
    : `m:${r.id}`;

const Pill: FC<{ label: string; active: boolean; onClick: () => void }> = ({ label, active, onClick }) => (
  <QamAction
    onPress={onClick}
    pressed={active}
    style={{
      padding: "5px 10px", borderRadius: 999, fontSize: theme.font.caption, cursor: "pointer",
      background: active ? theme.color.accent : "transparent",
      color: active ? theme.color.onAccent : theme.color.textPrimary,
      boxShadow: active ? "none" : `inset 0 0 0 1px ${theme.color.hairline}`,
      whiteSpace: "nowrap",
    }}
  >
    {label}
  </QamAction>
);

const OutlineBtn: FC<{
  onClick: () => void | Promise<void>;
  expanded?: boolean;
  children: ReactNode;
}> = ({ onClick, expanded, children }) => (
  <QamAction
    onPress={onClick}
    expanded={expanded}
    style={{
      flex: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 5,
      padding: "7px 8px", borderRadius: theme.radius.sm, cursor: "pointer",
      fontSize: theme.font.caption, color: theme.color.accent,
      boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
    }}
  >
    {children}
  </QamAction>
);

const SubItem: FC<{ label: string; on: boolean; onToggle: () => void }> = ({ label, on, onToggle }) => (
  <QamAction
    onPress={onToggle}
    pressed={on}
    style={{
      display: "flex", alignItems: "center", gap: theme.space.sm, cursor: "pointer",
      padding: "5px 8px", marginLeft: theme.space.md, borderRadius: theme.radius.sm,
      borderLeft: `2px solid ${theme.color.hairline}`,
    }}
  >
    <span
      style={{
        display: "flex", alignItems: "center", justifyContent: "center", width: 16, height: 16,
        flexShrink: 0, borderRadius: 4,
        background: on ? theme.color.accent : "transparent",
        boxShadow: on ? "none" : `inset 0 0 0 1px ${theme.color.hairline}`,
        color: theme.color.onAccent,
      }}
    >
      {on ? <LuCheck size={11} /> : null}
    </span>
    <span style={{ fontSize: theme.font.body, color: on ? theme.color.textPrimary : theme.color.textMuted }}>{label}</span>
  </QamAction>
);

const SectionLabel: FC<{ children: ReactNode }> = ({ children }) => (
  <span style={{ ...theme.sectionLabel }}>{children}</span>
);

const Note: FC<{ children: ReactNode }> = ({ children }) => (
  <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{children}</span>
);

const controlLabel = {
  fontSize: theme.font.caption,
  color: theme.color.textMuted,
} as const;

const RowAction: FC<{
  label: string;
  disabled?: boolean;
  onPress: () => void;
  children: ReactNode;
}> = ({ label, disabled, onPress, children }) => (
  <QamAction
    label={label}
    disabled={disabled}
    onPress={onPress}
    style={{
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      width: 28,
      height: 28,
      flexShrink: 0,
      borderRadius: theme.radius.sm,
      color: disabled ? theme.color.textMuted : theme.color.textPrimary,
      opacity: disabled ? 0.3 : 1,
      cursor: disabled ? "default" : "pointer",
    }}
  >
    {children}
  </QamAction>
);

export const HudSection: FC = () => {
  const { t } = useI18n();
  const { state, setModel, setEnabled, reload, reloadStatus, saveStatus, reset } = useHud();
  const [selected, setSelected] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  if (!state) {
    return (
      <PanelSectionRow>
        <Note>{t("hud.loading")}</Note>
      </PanelSectionRow>
    );
  }

  const m = state.model;
  const presets = Object.keys(state.presets).length ? state.presets : PRESETS;
  const patch = (p: Partial<HudModel>) => setModel({ ...m, ...p });
  const patchItems = (items: HudItem[]) => patch({ items });
  const setColor = (key: ColorKey, hex: string) => patch({ colors: { ...m.colors, [key]: hex } });

  const rows = listRows(m.items);

  const addEntries = (groupKey: string, ids: MetricId[]): AddEntry[] => {
    if ((BLOCK_GROUPS as string[]).includes(groupKey)) {
      const g = groupKey as BlockGroup;
      return hasBlock(m.items, g) ? [] : [{ kind: "block", group: g }];
    }
    return ids
      .filter((id) => state.catalog.includes(id) && !hasMetric(m.items, id))
      .map((id) => ({ kind: "metric", id }));
  };

  const add = (entry: AddEntry) => {
    const id: MetricId = entry.kind === "block" ? entry.group : entry.id;
    patchItems(addMetricItem(m.items, id));
    setSelected(entry.kind === "block" ? `b:${entry.group}` : `m:${id}`);
    setAdding(false);
  };
  const addText = () => {
    const id = `t${Date.now()}`;
    patchItems(addTextItem(m.items, id, ""));
    setSelected(`t:${id}`);
    setAdding(false);
  };
  const addSep = () => {
    const id = `s${Date.now()}`;
    patchItems(addSeparator(m.items, id));
    setSelected(`s:${id}`);
    setAdding(false);
  };
  const addSpace = () => {
    const id = `sp${Date.now()}`;
    patchItems(addSpacer(m.items, id, "small"));
    setSelected(`sp:${id}`);
    setAdding(false);
  };

  const applyPreset = (key: string) =>
    patchItems([
      ...presets[key].map((id) => ({ kind: "metric" as const, id })),
      ...m.items.filter((it) => it.kind !== "metric"),
    ]);

  const labelOf = (id: MetricId): string => {
    const it = m.items.find((x) => x.kind === "metric" && x.id === id);
    return (it && it.kind === "metric" && it.label) || "";
  };

  const renderEditor = (r: ListRow) => {
    if (r.kind === "separator") return null;
    if (r.kind === "spacer") {
      return (
        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
          <div style={{ ...segmentGroupStyle }}>
            {SPACER_SIZES.map((s) => (
              <QamAction
                key={s}
                onPress={() => patchItems(setSpacerSizeAt(m.items, r.index, s))}
                pressed={r.size === s}
                style={{ ...segmentItemStyle(r.size === s), flex: 1, padding: "5px 0" }}
              >
                {t(`hud.spacer.${s}`)}
              </QamAction>
            ))}
          </div>
          <Note>{t("hud.elem.spacer.hint")}</Note>
        </div>
      );
    }
    if (r.kind === "text") {
      return (
        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
          <TextField
            value={r.text}
            label={t("hud.elem.text.label")}
            onChange={(e) => patchItems(setTextAt(m.items, r.index, e.target.value))}
          />
          <Note>{t("hud.elem.value.textColor")}</Note>
        </div>
      );
    }
    if (r.kind === "block") {
      const groupName = t(`hud.color.${r.group}`);
      return (
        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
          <Note>{t("hud.block.hint")}</Note>
          <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
            {blockMetricIds(r.group).map((id) => (
              <SubItem key={id} label={t(`hud.metric.${id}`)} on={hasMetric(m.items, id)} onToggle={() => patchItems(toggleMetricItem(m.items, id))} />
            ))}
          </div>
          {canLabel(r.group) ? (
            <TextField
              value={labelOf(r.group)}
              label={t("hud.elem.label")}
              onChange={(e) => patchItems(setMetricLabel(m.items, r.group, e.target.value))}
            />
          ) : null}
          <div style={{ display: "flex", alignItems: "center", gap: theme.space.sm }}>
            <ColorPicker label={t("hud.elem.groupColor", { group: groupName })} value={m.colors[r.group]} onChange={(hex) => setColor(r.group, hex)} />
            <Note>{t("hud.elem.groupColor", { group: groupName })}</Note>
          </div>
        </div>
      );
    }
    // standalone metric line
    const id = r.id;
    const colorKey: ColorKey | null = id === "fps" ? "fps" : id === "frametime" ? "frametime" : null;
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
        {canLabel(id) ? (
          <TextField
            value={labelOf(id)}
            label={t("hud.elem.label")}
            onChange={(e) => patchItems(setMetricLabel(m.items, id, e.target.value))}
          />
        ) : null}
        {colorKey ? (
          <div style={{ display: "flex", alignItems: "center", gap: theme.space.sm }}>
            <ColorPicker label={t(`hud.color.${colorKey}`)} value={m.colors[colorKey]} onChange={(hex) => setColor(colorKey, hex)} />
            <Note>{t(`hud.color.${colorKey}`)}</Note>
          </div>
        ) : (
          <Note>{t("hud.elem.value.textColor")}</Note>
        )}
      </div>
    );
  };

  const rowTitle = (r: ListRow): string => {
    if (r.kind === "block") return t(`hud.group.${r.group}`);
    if (r.kind === "text") return r.text || t("hud.elem.text.empty");
    if (r.kind === "separator") return t("hud.elem.separator");
    if (r.kind === "spacer") return `${t("hud.elem.spacer")} · ${t(`hud.spacer.${r.size}`)}`;
    return (canLabel(r.id) && labelOf(r.id)) || t(`hud.metric.${r.id}`);
  };

  const openReset = () => {
    showModal(
      <ConfirmDialog
        title={t("hud.reset.confirm.title")}
        desc={t("hud.reset.confirm.desc")}
        confirmLabel={t("hud.reset")}
        cancelLabel={t("hud.reset.cancel")}
        onConfirm={reset}
        icon={<LuRotateCcw size={18} />}
      />,
    );
  };

  return (
    <PanelSectionRow>
      <div
        data-testid="hud-stack"
        style={{
          display: "flex",
          flexDirection: "column",
          gap: theme.space.md,
          minWidth: 0,
          marginBottom: theme.space.card,
        }}
      >
        <div style={{ ...card, display: "flex", flexDirection: "column", gap: theme.space.sm }}>
          <HudPreview model={m} values={state.values} />
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: theme.space.sm }}>
            <SectionLabel>{t("hud.title")}</SectionLabel>
            <span
              aria-live="polite"
              style={{
                padding: "3px 7px",
                borderRadius: 999,
                fontSize: theme.font.caption,
                color: state.applyStatus === "failed" || state.applyStatus === "unavailable"
                  ? theme.color.danger
                  : state.applyStatus === "applied"
                    ? theme.color.accent
                    : theme.color.textMuted,
                boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
              }}
            >
              {t(`hud.status.${state.applyStatus}`)}
            </span>
          </div>
          <ToggleField label={t("hud.show")} checked={m.enabled} onChange={setEnabled} bottomSeparator="none" />
          <div aria-live="polite" style={{ display: "flex", gap: theme.space.sm }}>
            <OutlineBtn onClick={reload}>
              {reloadStatus === "busy" ? (
                <><Spinner style={{ width: 13, height: 13 }} /> {t("hud.reload.busy")}</>
              ) : reloadStatus === "ok" ? (
                <><LuCheck size={13} /> {t("hud.reload.ok")}</>
              ) : reloadStatus === "pending" ? (
                <><LuRefreshCw size={13} /> {t("hud.reload.pending")}</>
              ) : reloadStatus === "error" ? (
                <><LuTriangleAlert size={13} /> {t("hud.reload.error")}</>
              ) : (
                <><LuRefreshCw size={13} /> {t("hud.reload")}</>
              )}
            </OutlineBtn>
          </div>
          {state.capability === "inactive" ? (
            <Note>{t("hud.inactive")}</Note>
          ) : state.capability === "unsupported" ? (
            <Note>{t("hud.unsupported")}</Note>
          ) : (
            <Note>{t("hud.show.hint")}</Note>
          )}
          {saveStatus === "error" && <Note>{t("hud.save.error")}</Note>}
          <div style={{ display: "flex", gap: theme.space.sm, minWidth: 0 }}>
            {Object.keys(presets).map((key) => {
              const metricIds = m.items
                .filter((item): item is Extract<HudItem, { kind: "metric" }> => item.kind === "metric")
                .map((item) => item.id);
              const active = metricIds.length === presets[key].length
                && metricIds.every((id, index) => presets[key][index] === id);
              return (
                <QamAction
                  key={key}
                  onPress={() => applyPreset(key)}
                  pressed={active}
                  style={{
                    flex: 1,
                    minWidth: 0,
                    textAlign: "center",
                    padding: "6px 4px",
                    borderRadius: theme.radius.sm,
                    fontSize: theme.font.caption,
                    cursor: "pointer",
                    color: active ? theme.color.onAccent : theme.color.textPrimary,
                    background: active ? theme.color.accent : "transparent",
                    boxShadow: active ? "none" : `inset 0 0 0 1px ${theme.color.hairline}`,
                  }}
                >
                  {t(`hud.preset.${key}`)}
                </QamAction>
              );
            })}
          </div>
        </div>

        <div style={{ ...card, display: "flex", flexDirection: "column", gap: theme.space.sm }}>
          <SectionLabel>{t("hud.elements")}</SectionLabel>
          <Note>{t("hud.elements.hint")}</Note>
          {rows.length === 0 && <Note>{t("hud.order.empty")}</Note>}
          {rows.map((r, i) => {
            const key = rowKey(r);
            const isSel = selected === key;
            const isBlock = r.kind === "block";
            const editable = hasLocalEditor(r);
            const active = isBlock ? blockMetricIds(r.group).filter((id) => hasMetric(m.items, id)).length : 0;
            const total = isBlock ? blockMetricIds(r.group).length : 0;
            const title = (
              <>
                {editable && (
                  <LuChevronRight
                    size={12}
                    style={{
                      flexShrink: 0,
                      transform: isSel ? "rotate(90deg)" : "none",
                      transition: "transform 120ms",
                      color: isSel ? theme.color.accent : theme.color.textMuted,
                    }}
                  />
                )}
                <span style={{ flex: 1, minWidth: 0, fontSize: theme.font.body, fontWeight: isBlock ? 600 : 400, color: theme.color.textPrimary, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {rowTitle(r)}
                </span>
                {isBlock && (
                  <span style={{ flexShrink: 0, fontSize: theme.font.caption, color: theme.color.textMuted }}>{active}/{total}</span>
                )}
              </>
            );
            return (
              <div
                key={key}
                style={{
                  display: "flex", flexDirection: "column", gap: theme.space.xs,
                  ...(isBlock
                    ? { padding: theme.space.xs, borderRadius: theme.radius.sm, background: "rgba(255,255,255,0.03)", boxShadow: `inset 0 0 0 1px ${theme.color.hairline}` }
                    : {}),
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs }}>
                  {editable ? (
                    <QamAction
                      onPress={() => setSelected(isSel ? null : key)}
                      expanded={isSel}
                      style={{
                        flex: 1, minWidth: 0, display: "flex", alignItems: "center", gap: 6, cursor: "pointer",
                        padding: "4px 6px", borderRadius: theme.radius.sm,
                        background: isSel ? "rgba(255,255,255,0.05)" : "transparent",
                      }}
                    >
                      {title}
                    </QamAction>
                  ) : (
                    <div
                      style={{
                        flex: 1,
                        minWidth: 0,
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                        padding: "4px 6px",
                      }}
                    >
                      {title}
                    </div>
                  )}
                  <RowAction label={t("hud.move.up")} disabled={i === 0} onPress={() => patchItems(moveRow(m.items, i, -1))}><LuChevronUp size={14} /></RowAction>
                  <RowAction label={t("hud.move.down")} disabled={i === rows.length - 1} onPress={() => patchItems(moveRow(m.items, i, 1))}><LuChevronDown size={14} /></RowAction>
                  <RowAction label={t("hud.remove")} onPress={() => { patchItems(removeRow(m.items, i)); if (isSel) setSelected(null); }}><LuX size={13} /></RowAction>
                </div>
                {editable && isSel && (
                  <div style={{ padding: theme.space.sm, borderRadius: theme.radius.sm, ...(isBlock ? {} : { boxShadow: `inset 0 0 0 1px ${theme.color.hairline}` }) }}>
                    {renderEditor(r)}
                  </div>
                )}
              </div>
            );
          })}

          <OutlineBtn onClick={() => setAdding((open) => !open)} expanded={adding}>
            {adding ? <LuX size={14} /> : <LuPlus size={14} />}
            {adding ? t("hud.close") : t("hud.add")}
          </OutlineBtn>
          {adding && (
            <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm, padding: theme.space.sm, borderRadius: theme.radius.sm, boxShadow: `inset 0 0 0 1px ${theme.color.hairline}` }}>
              {GROUPS.map((g) => {
                const entries = addEntries(g.key, g.ids);
                if (entries.length === 0) return null;
                return (
                  <div key={g.key} style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
                    <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t(`hud.group.${g.key}`)}</span>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: theme.space.xs }}>
                      {entries.map((e) => (
                        <Pill
                          key={e.kind === "block" ? `b:${e.group}` : e.id}
                          label={e.kind === "block" ? t(`hud.group.${e.group}`) : t(`hud.metric.${e.id}`)}
                          active={false}
                          onClick={() => add(e)}
                        />
                      ))}
                    </div>
                  </div>
                );
              })}
              <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
                <OutlineBtn onClick={addText}><LuType size={13} /> {t("hud.elem.addText")}</OutlineBtn>
                <OutlineBtn onClick={addSep}><LuMinus size={13} /> {t("hud.elem.addSeparator")}</OutlineBtn>
                <OutlineBtn onClick={addSpace}><LuMoveVertical size={13} /> {t("hud.elem.addSpacer")}</OutlineBtn>
              </div>
            </div>
          )}
        </div>

      <HudDisclosure
        id="hud-appearance"
        icon={<LuSlidersHorizontal size={16} />}
        title={t("hud.style")}
        summary={`${t(`hud.layout.${m.layout}`)} · ${t(`hud.position.${m.position}`)}`}
        defaultOpen={false}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.md }}>
          <Note>{t("hud.style.scope")}</Note>
          <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm, minWidth: 0 }}>
            <span style={controlLabel}>{t("hud.layout")}</span>
            <div style={{ ...segmentGroupStyle, width: "100%", minWidth: 0 }}>
              {LAYOUTS.map((l) => (
                <QamAction key={l} onPress={() => patch({ layout: l })} pressed={m.layout === l} style={{ ...segmentItemStyle(m.layout === l), flex: 1, padding: "5px 0" }}>
                  {t(`hud.layout.${l}`)}
                </QamAction>
              ))}
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm, minWidth: 0 }}>
            <span style={controlLabel}>{t("hud.position")}</span>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: theme.space.xs, width: "100%" }}>
              {POSITIONS.map(({ id, Icon }) => {
                const active = m.position === id;
                return (
                  <QamAction
                    key={id}
                    label={t(`hud.position.${id}`)}
                    onPress={() => patch({ position: id })}
                    pressed={active}
                    style={{
                      display: "flex", alignItems: "center", justifyContent: "center", height: 32,
                      borderRadius: theme.radius.sm, cursor: "pointer",
                      color: active ? theme.color.onAccent : theme.color.textPrimary,
                      background: active ? theme.color.accent : "transparent",
                      boxShadow: active ? "none" : `inset 0 0 0 1px ${theme.color.hairline}`,
                    }}
                  >
                    <Icon size={14} />
                  </QamAction>
                );
              })}
            </div>
          </div>

          <HudSliderRow label={t("hud.size")} value={m.fontSize} min={12} max={64} step={1} unit="px" onChange={(v) => patch({ fontSize: v })} />
          <HudSliderRow label={t("hud.sizeText")} value={m.fontSizeText} min={12} max={64} step={1} unit="px" onChange={(v) => patch({ fontSizeText: v })} />

          <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm, minWidth: 0 }}>
            <span style={controlLabel}>{t("hud.tempUnit")}</span>
            <div style={{ ...segmentGroupStyle, width: "100%", minWidth: 0 }}>
              {TEMP_UNITS.map((u) => (
                <QamAction key={u} onPress={() => patch({ tempUnit: u })} pressed={m.tempUnit === u} style={{ ...segmentItemStyle(m.tempUnit === u), flex: 1, padding: "5px 0" }}>
                  {t(`hud.tempUnit.${u}`)}
                </QamAction>
              ))}
            </div>
          </div>

          <HudSliderRow label={t("hud.opacity")} value={Math.round(m.background.alpha * 100)} min={0} max={100} step={5} unit="percent" onChange={(v) => patch({ background: { ...m.background, alpha: v / 100 } })} />

          <ToggleField label={t("hud.noSmallFont")} checked={m.noSmallFont} onChange={(v) => patch({ noSmallFont: v })} bottomSeparator="none" />
          <ToggleField label={t("hud.textOutline")} checked={m.textOutline} onChange={(v) => patch({ textOutline: v })} bottomSeparator="none" />
          <ToggleField label={t("hud.roundCorners")} checked={m.background.roundCorners} onChange={(v) => patch({ background: { ...m.background, roundCorners: v } })} bottomSeparator="none" />
          <Note>{t("hud.style.hint")}</Note>
        </div>
      </HudDisclosure>

      <HudDisclosure
        id="hud-colors"
        icon={<LuPalette size={16} />}
        title={t("hud.colors")}
        summary={t("hud.colors.summary")}
        defaultOpen={false}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.md }}>
          <Note>{t("hud.colors.hint")}</Note>
          <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm, minWidth: 0 }}>
            {COLOR_KEYS.map((key) => (
              <div key={key} style={{ display: "flex", alignItems: "center", gap: theme.space.sm }}>
                <ColorPicker label={t(`hud.color.${key}`)} value={m.colors[key]} onChange={(hex) => setColor(key, hex)} />
                <Note>{t(`hud.color.${key}`)}</Note>
              </div>
            ))}
          </div>
        </div>
      </HudDisclosure>

      <HudDisclosure
        id="hud-advanced"
        icon={<LuSettings2 size={16} />}
        title={t("hud.advanced")}
        summary={t("hud.advanced.summary")}
        defaultOpen={false}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.md }}>
          <HudSliderRow label={t("hud.cellpaddingY")} value={Math.round(m.cellpaddingY * 100)} min={-30} max={50} step={1} unit="signed-decimal" onChange={(v) => patch({ cellpaddingY: v / 100 })} />
          <HudSliderRow label={t("hud.fontScale")} value={Math.round(m.fontScale * 100)} min={50} max={200} step={5} unit="multiplier" onChange={(v) => patch({ fontScale: v / 100 })} />
          <HudSliderRow label={t("hud.textAlpha")} value={Math.round(m.alpha * 100)} min={0} max={100} step={5} unit="percent" onChange={(v) => patch({ alpha: v / 100 })} />
          <HudSliderRow label={t("hud.outlineThickness")} value={Math.round(m.textOutlineThickness * 10)} min={0} max={40} step={1} unit="decimal" onChange={(v) => patch({ textOutlineThickness: v / 10 })} />
          <HudSliderRow label={t("hud.offsetX")} value={m.offsetX} min={-200} max={200} step={2} unit="px" onChange={(v) => patch({ offsetX: v })} />
          <HudSliderRow label={t("hud.offsetY")} value={m.offsetY} min={-200} max={200} step={2} unit="px" onChange={(v) => patch({ offsetY: v })} />
          <ToggleField label={t("hud.compact")} checked={m.compact} onChange={(v) => patch({ compact: v })} bottomSeparator="none" />
          <ToggleField label={t("hud.noMargin")} checked={m.noMargin} onChange={(v) => patch({ noMargin: v })} bottomSeparator="none" />
          <div style={{ display: "flex", alignItems: "center", gap: theme.space.sm }}>
            <ColorPicker label={t("hud.separatorColor")} value={m.separatorColor ?? "ffffff"} onChange={(hex) => patch({ separatorColor: hex })} />
            <Note>{t("hud.separatorColor")}</Note>
          </div>
          <Note>{t("hud.separatorColor.hint")}</Note>
          <Note>{t("hud.advanced.hint")}</Note>
        </div>
      </HudDisclosure>

        <QamAction
          onPress={openReset}
          style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 6, padding: "8px 0", borderRadius: theme.radius.sm, cursor: "pointer", color: theme.color.textMuted, fontSize: theme.font.caption }}
        >
          <LuRotateCcw size={13} /> {t("hud.reset")}
        </QamAction>
      </div>
    </PanelSectionRow>
  );
};
