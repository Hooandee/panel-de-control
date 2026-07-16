import { FC, useState } from "react";
import { PanelSectionRow, Focusable, ToggleField, TextField, Spinner } from "@decky/ui";
import {
  LuArrowUpLeft, LuArrowUpRight, LuArrowDownLeft, LuArrowDownRight,
  LuChevronUp, LuChevronDown, LuChevronRight, LuX, LuRotateCcw, LuRefreshCw,
  LuType, LuMinus, LuPlus, LuMoveVertical, LuCheck,
} from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { useHud } from "../mangohud/useHud";
import { HudPreview } from "../components/HudPreview";
import { ContainedSlider } from "../components/ContainedSlider";
import { ColorPicker } from "../components/ColorPicker";
import { segmentGroupStyle, segmentItemStyle } from "../components/segmented";
import {
  BLOCK_GROUPS, BlockGroup, COLOR_KEYS, ColorKey, GROUPS, HudItem, HudLayout, HudModel,
  HudPosition, ListRow, MetricId, SPACER_SIZES, TempUnit, PRESETS,
  addMetricItem, addSeparator, addSpacer, addTextItem, blockMetricIds, canLabel, hasBlock, hasMetric,
  listRows, moveRow, removeRow, setMetricLabel, setSpacerSizeAt, setTextAt, toggleMetricItem,
} from "../mangohud/model";

const card = { ...theme.card, padding: theme.space.md, overflow: "hidden" } as const;

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
  <Focusable
    onActivate={onClick}
    onClick={onClick}
    style={{
      padding: "5px 10px", borderRadius: 999, fontSize: theme.font.caption, cursor: "pointer",
      background: active ? theme.color.accent : "transparent",
      color: active ? theme.color.onAccent : theme.color.textPrimary,
      boxShadow: active ? "none" : `inset 0 0 0 1px ${theme.color.hairline}`,
      whiteSpace: "nowrap",
    }}
  >
    {label}
  </Focusable>
);

const IconBtn: FC<{ label: string; onClick: () => void; children: React.ReactNode; muted?: boolean }> = ({ label, onClick, children, muted }) => (
  <Focusable
    onActivate={onClick}
    onClick={onClick}
    title={label}
    style={{
      display: "flex", alignItems: "center", justifyContent: "center", width: 26, height: 26,
      borderRadius: theme.radius.sm, cursor: "pointer", flexShrink: 0,
      color: muted ? theme.color.textMuted : theme.color.textPrimary,
      boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
    }}
  >
    {children}
  </Focusable>
);

const OutlineBtn: FC<{ onClick: () => void; children: React.ReactNode }> = ({ onClick, children }) => (
  <Focusable
    onActivate={onClick}
    onClick={onClick}
    style={{
      flex: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 5,
      padding: "7px 8px", borderRadius: theme.radius.sm, cursor: "pointer",
      fontSize: theme.font.caption, color: theme.color.accent,
      boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
    }}
  >
    {children}
  </Focusable>
);

// An indented, toggleable sub-metric row inside a group container. The check box on
// the left reads on/off; activating it includes/excludes the sub-metric.
const SubItem: FC<{ label: string; on: boolean; onToggle: () => void }> = ({ label, on, onToggle }) => (
  <Focusable
    onActivate={onToggle}
    onClick={onToggle}
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
  </Focusable>
);

const StyleRow: FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div style={{ display: "flex", alignItems: "center", gap: theme.space.md }}>
    <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted, width: 74, flexShrink: 0 }}>{label}</span>
    {children}
  </div>
);

const SectionLabel: FC<{ children: React.ReactNode }> = ({ children }) => (
  <span style={{ ...theme.sectionLabel }}>{children}</span>
);

const Note: FC<{ children: React.ReactNode }> = ({ children }) => (
  <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{children}</span>
);

export const HudSection: FC = () => {
  const { t } = useI18n();
  const { state, setModel, setEnabled, reload, reloadStatus, reset } = useHud();
  const [selected, setSelected] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [advanced, setAdvanced] = useState(false);

  if (!state) {
    return (
      <PanelSectionRow>
        <Note>{t("hud.loading")}</Note>
      </PanelSectionRow>
    );
  }

  const m = state.model;
  const patch = (p: Partial<HudModel>) => setModel({ ...m, ...p });
  const patchItems = (items: HudItem[]) => patch({ items });
  const setColor = (key: ColorKey, hex: string) => patch({ colors: { ...m.colors, [key]: hex } });

  if (!state.supported) {
    return (
      <PanelSectionRow>
        <div style={{ ...card }}>
          <div style={{ fontSize: theme.font.body, color: theme.color.textPrimary, marginBottom: theme.space.xs }}>{t("hud.title")}</div>
          <Note>{t("hud.unsupported")}</Note>
        </div>
      </PanelSectionRow>
    );
  }

  const rows = listRows(m.items);

  const addEntries = (groupKey: string, ids: MetricId[]): AddEntry[] => {
    if ((BLOCK_GROUPS as string[]).includes(groupKey)) {
      const g = groupKey as BlockGroup;
      return hasBlock(m.items, g) ? [] : [{ kind: "block", group: g }];
    }
    return ids.filter((id) => !hasMetric(m.items, id)).map((id) => ({ kind: "metric", id }));
  };

  const add = (entry: AddEntry) => {
    const id: MetricId = entry.kind === "block" ? entry.group : entry.id;
    patchItems(addMetricItem(m.items, id));
    setSelected(entry.kind === "block" ? `b:${entry.group}` : `m:${id}`);
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
      ...PRESETS[key].map((id) => ({ kind: "metric" as const, id })),
      ...m.items.filter((it) => it.kind !== "metric"),
    ]);

  const labelOf = (id: MetricId): string => {
    const it = m.items.find((x) => x.kind === "metric" && x.id === id);
    return (it && it.kind === "metric" && it.label) || "";
  };

  // Inline editor for a selected list row.
  const renderEditor = (r: ListRow) => {
    if (r.kind === "separator") {
      return <Note>{t("hud.elem.separator.hint")}</Note>;
    }
    if (r.kind === "spacer") {
      return (
        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
          <div style={{ ...segmentGroupStyle }}>
            {SPACER_SIZES.map((s) => (
              <Focusable key={s} onActivate={() => patchItems(setSpacerSizeAt(m.items, r.index, s))} onClick={() => patchItems(setSpacerSizeAt(m.items, r.index, s))} style={{ ...segmentItemStyle(r.size === s), flex: 1, padding: "5px 0" }}>
                {t(`hud.spacer.${s}`)}
              </Focusable>
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

  return (
    <>
      {/* Preview (hero) + master toggle + live reload */}
      <PanelSectionRow>
        <div style={{ ...card, display: "flex", flexDirection: "column", gap: theme.space.sm }}>
          <HudPreview model={m} />
          <ToggleField label={t("hud.show")} checked={m.enabled} onChange={setEnabled} bottomSeparator="none" />
          <div style={{ display: "flex", gap: theme.space.sm }}>
            <OutlineBtn onClick={reload}>
              {reloadStatus === "busy" ? (
                <><Spinner style={{ width: 13, height: 13 }} /> {t("hud.reload.busy")}</>
              ) : reloadStatus === "ok" ? (
                <><LuCheck size={13} /> {t("hud.reload.ok")}</>
              ) : (
                <><LuRefreshCw size={13} /> {t("hud.reload")}</>
              )}
            </OutlineBtn>
          </div>
          <Note>{t("hud.show.hint")}</Note>
        </div>
      </PanelSectionRow>

      {/* Presets */}
      <PanelSectionRow>
        <div style={{ display: "flex", gap: theme.space.sm }}>
          {Object.keys(PRESETS).map((key) => (
            <Focusable
              key={key}
              onActivate={() => applyPreset(key)}
              onClick={() => applyPreset(key)}
              style={{
                flex: 1, textAlign: "center", padding: "6px 4px", borderRadius: theme.radius.sm,
                fontSize: theme.font.caption, cursor: "pointer", color: theme.color.textPrimary,
                boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
              }}
            >
              {t(`hud.preset.${key}`)}
            </Focusable>
          ))}
        </div>
      </PanelSectionRow>

      {/* Elements: block/line list + select-to-edit + "+" picker */}
      <PanelSectionRow>
        <div style={{ ...card, display: "flex", flexDirection: "column", gap: theme.space.sm }}>
          <SectionLabel>{t("hud.elements")}</SectionLabel>
          <Note>{t("hud.elements.hint")}</Note>
          {rows.length === 0 && <Note>{t("hud.order.empty")}</Note>}
          {rows.map((r, i) => {
            const key = rowKey(r);
            const isSel = selected === key;
            const isBlock = r.kind === "block";
            // A group renders as a titled CONTAINER (subtle border + fill) so it's clear
            // its sub-metrics are children; standalone lines have no container chrome.
            const active = isBlock ? blockMetricIds(r.group).filter((id) => hasMetric(m.items, id)).length : 0;
            const total = isBlock ? blockMetricIds(r.group).length : 0;
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
                  <Focusable
                    onActivate={() => setSelected(isSel ? null : key)}
                    onClick={() => setSelected(isSel ? null : key)}
                    style={{
                      flex: 1, minWidth: 0, display: "flex", alignItems: "center", gap: 6, cursor: "pointer",
                      padding: "4px 6px", borderRadius: theme.radius.sm,
                      background: isSel ? "rgba(255,255,255,0.05)" : "transparent",
                    }}
                  >
                    <LuChevronRight size={12} style={{ flexShrink: 0, transform: isSel ? "rotate(90deg)" : "none", transition: "transform 120ms", color: isSel ? theme.color.accent : theme.color.textMuted }} />
                    <span style={{ flex: 1, minWidth: 0, fontSize: theme.font.body, fontWeight: isBlock ? 600 : 400, color: theme.color.textPrimary, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {rowTitle(r)}
                    </span>
                    {isBlock && (
                      <span style={{ flexShrink: 0, fontSize: theme.font.caption, color: theme.color.textMuted }}>{active}/{total}</span>
                    )}
                  </Focusable>
                  <IconBtn label={t("hud.move.up")} onClick={() => patchItems(moveRow(m.items, i, -1))}><LuChevronUp size={14} /></IconBtn>
                  <IconBtn label={t("hud.move.down")} onClick={() => patchItems(moveRow(m.items, i, 1))}><LuChevronDown size={14} /></IconBtn>
                  <IconBtn label={t("hud.remove")} muted onClick={() => { patchItems(removeRow(m.items, i)); if (isSel) setSelected(null); }}><LuX size={13} /></IconBtn>
                </div>
                {isSel && (
                  <div style={{ padding: theme.space.sm, borderRadius: theme.radius.sm, ...(isBlock ? {} : { boxShadow: `inset 0 0 0 1px ${theme.color.hairline}` }) }}>
                    {renderEditor(r)}
                  </div>
                )}
              </div>
            );
          })}

          {/* "+" add picker (only metrics not already added — no duplicates) */}
          {adding ? (
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
              <div style={{ display: "flex", gap: theme.space.sm }}>
                <OutlineBtn onClick={addText}><LuType size={13} /> {t("hud.elem.addText")}</OutlineBtn>
                <OutlineBtn onClick={addSep}><LuMinus size={13} /> {t("hud.elem.addSeparator")}</OutlineBtn>
                <OutlineBtn onClick={addSpace}><LuMoveVertical size={13} /> {t("hud.elem.addSpacer")}</OutlineBtn>
              </div>
            </div>
          ) : (
            <OutlineBtn onClick={() => setAdding(true)}><LuPlus size={14} /> {t("hud.add")}</OutlineBtn>
          )}
        </div>
      </PanelSectionRow>

      {/* Global style — whole HUD */}
      <PanelSectionRow>
        <div style={{ ...card, display: "flex", flexDirection: "column", gap: theme.space.md }}>
          <SectionLabel>{t("hud.style")}</SectionLabel>
          <Note>{t("hud.style.scope")}</Note>

          <StyleRow label={t("hud.layout")}>
            <div style={{ ...segmentGroupStyle, flex: 1 }}>
              {LAYOUTS.map((l) => (
                <Focusable key={l} onActivate={() => patch({ layout: l })} onClick={() => patch({ layout: l })} style={{ ...segmentItemStyle(m.layout === l), flex: 1, padding: "5px 0" }}>
                  {t(`hud.layout.${l}`)}
                </Focusable>
              ))}
            </div>
          </StyleRow>

          <StyleRow label={t("hud.position")}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4, width: 72 }}>
              {POSITIONS.map(({ id, Icon }) => {
                const active = m.position === id;
                return (
                  <Focusable
                    key={id}
                    onActivate={() => patch({ position: id })}
                    onClick={() => patch({ position: id })}
                    style={{
                      display: "flex", alignItems: "center", justifyContent: "center", height: 28,
                      borderRadius: theme.radius.sm, cursor: "pointer",
                      color: active ? theme.color.onAccent : theme.color.textPrimary,
                      background: active ? theme.color.accent : "transparent",
                      boxShadow: active ? "none" : `inset 0 0 0 1px ${theme.color.hairline}`,
                    }}
                  >
                    <Icon size={14} />
                  </Focusable>
                );
              })}
            </div>
          </StyleRow>

          <StyleRow label={t("hud.size")}>
            <div style={{ flex: 1 }}>
              <ContainedSlider value={m.fontSize} min={12} max={64} step={1} showValue onChange={(v) => patch({ fontSize: v })} />
            </div>
          </StyleRow>

          <StyleRow label={t("hud.sizeText")}>
            <div style={{ flex: 1 }}>
              <ContainedSlider value={m.fontSizeText} min={12} max={64} step={1} showValue onChange={(v) => patch({ fontSizeText: v })} />
            </div>
          </StyleRow>

          <StyleRow label={t("hud.tempUnit")}>
            <div style={{ ...segmentGroupStyle, flex: 1 }}>
              {TEMP_UNITS.map((u) => (
                <Focusable key={u} onActivate={() => patch({ tempUnit: u })} onClick={() => patch({ tempUnit: u })} style={{ ...segmentItemStyle(m.tempUnit === u), flex: 1, padding: "5px 0" }}>
                  {t(`hud.tempUnit.${u}`)}
                </Focusable>
              ))}
            </div>
          </StyleRow>

          <StyleRow label={t("hud.opacity")}>
            <div style={{ flex: 1 }}>
              <ContainedSlider value={Math.round(m.background.alpha * 100)} min={0} max={100} step={5} showValue onChange={(v) => patch({ background: { ...m.background, alpha: v / 100 } })} />
            </div>
          </StyleRow>

          <ToggleField label={t("hud.noSmallFont")} checked={m.noSmallFont} onChange={(v) => patch({ noSmallFont: v })} bottomSeparator="none" />
          <ToggleField label={t("hud.textOutline")} checked={m.textOutline} onChange={(v) => patch({ textOutline: v })} bottomSeparator="none" />
          <ToggleField label={t("hud.roundCorners")} checked={m.background.roundCorners} onChange={(v) => patch({ background: { ...m.background, roundCorners: v } })} bottomSeparator="none" />

          {/* Advanced — extra global style knobs, collapsed by default */}
          <Focusable
            onActivate={() => setAdvanced((v) => !v)}
            onClick={() => setAdvanced((v) => !v)}
            style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}
          >
            {advanced ? <LuChevronDown size={14} color={theme.color.textMuted} /> : <LuChevronRight size={14} color={theme.color.textMuted} />}
            <SectionLabel>{t("hud.advanced")}</SectionLabel>
          </Focusable>
          {advanced && (
            <div style={{ display: "flex", flexDirection: "column", gap: theme.space.md }}>
              <StyleRow label={t("hud.cellpaddingY")}>
                <div style={{ flex: 1 }}>
                  <ContainedSlider value={Math.round(m.cellpaddingY * 100)} min={-30} max={50} step={1} showValue onChange={(v) => patch({ cellpaddingY: v / 100 })} />
                </div>
              </StyleRow>
              <StyleRow label={t("hud.fontScale")}>
                <div style={{ flex: 1 }}>
                  <ContainedSlider value={Math.round(m.fontScale * 100)} min={50} max={200} step={5} showValue onChange={(v) => patch({ fontScale: v / 100 })} />
                </div>
              </StyleRow>
              <StyleRow label={t("hud.textAlpha")}>
                <div style={{ flex: 1 }}>
                  <ContainedSlider value={Math.round(m.alpha * 100)} min={0} max={100} step={5} showValue onChange={(v) => patch({ alpha: v / 100 })} />
                </div>
              </StyleRow>
              <StyleRow label={t("hud.offsetX")}>
                <div style={{ flex: 1 }}>
                  <ContainedSlider value={m.offsetX} min={-200} max={200} step={2} showValue onChange={(v) => patch({ offsetX: v })} />
                </div>
              </StyleRow>
              <StyleRow label={t("hud.offsetY")}>
                <div style={{ flex: 1 }}>
                  <ContainedSlider value={m.offsetY} min={-200} max={200} step={2} showValue onChange={(v) => patch({ offsetY: v })} />
                </div>
              </StyleRow>
              <ToggleField label={t("hud.compact")} checked={m.compact} onChange={(v) => patch({ compact: v })} bottomSeparator="none" />
              <ToggleField label={t("hud.noMargin")} checked={m.noMargin} onChange={(v) => patch({ noMargin: v })} bottomSeparator="none" />
              <Note>{t("hud.advanced.hint")}</Note>
            </div>
          )}

          {/* Colours — per category + global text/background/outline */}
          <SectionLabel>{t("hud.colors")}</SectionLabel>
          <Note>{t("hud.colors.hint")}</Note>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: theme.space.sm }}>
            {COLOR_KEYS.map((key) => (
              <div key={key} style={{ display: "flex", alignItems: "center", gap: theme.space.sm }}>
                <ColorPicker label={t(`hud.color.${key}`)} value={m.colors[key]} onChange={(hex) => setColor(key, hex)} />
                <Note>{t(`hud.color.${key}`)}</Note>
              </div>
            ))}
          </div>

          {/* Separator colour applies only to the horizontal native divider. */}
          <StyleRow label={t("hud.separatorColor")}>
            <ColorPicker label={t("hud.separatorColor")} value={m.separatorColor ?? "ffffff"} onChange={(hex) => patch({ separatorColor: hex })} />
          </StyleRow>
          <Note>{t("hud.separatorColor.hint")}</Note>

          <Note>{t("hud.style.hint")}</Note>
        </div>
      </PanelSectionRow>

      {/* Reset */}
      <PanelSectionRow>
        <Focusable
          onActivate={reset}
          onClick={reset}
          style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 6, padding: "8px 0", borderRadius: theme.radius.sm, cursor: "pointer", color: theme.color.textMuted, fontSize: theme.font.caption }}
        >
          <LuRotateCcw size={13} /> {t("hud.reset")}
        </Focusable>
      </PanelSectionRow>
    </>
  );
};
