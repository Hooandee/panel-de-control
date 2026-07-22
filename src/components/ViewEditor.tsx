import { FC, Fragment, useState } from "react";
import { ModalRoot, showModal, Focusable, TextField, ButtonItem } from "@decky/ui";
import { LuChevronUp, LuChevronDown, LuPlus, LuX, LuCheck } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { FocusRoot } from "./FocusRoot";
import { IconAction } from "./IconAction";
import { TABS, PICKABLE_BLOCKS, blockOrder, CATEGORY_IDS } from "../customize/manifest";
import { move } from "../customize/layout";
import { getPresent } from "../customize/present";
import { useViews, renameView, setViewIcon, setViewBlocks, deleteView } from "../customize/viewStore";
import { VIEW_ICON_KEYS, ViewIconKey } from "../customize/views";
import { viewIconNode } from "../customize/viewIcons";

/** Block metadata (label + icon) by id, across every pickable section. */
const META = new Map(
  Object.values(PICKABLE_BLOCKS).flat().map((b) => [b.id, b] as const),
);

/** Ids a category offers to a view: the machine's real blocks (present, else the
 *  manifest) plus fixed cores (e.g. the TDP arc) that aren't reorderable in their
 *  own tab but can live in a view. */
function pickableIds(cat: string): string[] {
  const base = getPresent(cat) ?? blockOrder(cat);
  const extras = (PICKABLE_BLOCKS[cat] ?? [])
    .map((b) => b.id)
    .filter((id) => !blockOrder(cat).includes(id));
  return [...extras, ...base];
}

const ViewEditorBody: FC<{ viewId: string; closeModal?: () => void }> = ({ viewId, closeModal }) => {
  const { t } = useI18n();
  const view = useViews().find((v) => v.id === viewId);
  const [confirmDel, setConfirmDel] = useState(false);
  if (!view) return null;

  const blocks = view.blocks;
  const label = (id: string) => {
    const m = META.get(id);
    return m ? t(m.labelKey) : id;
  };
  const removeBlock = (id: string) => setViewBlocks(viewId, blocks.filter((b) => b !== id));
  const addBlock = (id: string) => setViewBlocks(viewId, [...blocks, id]);
  const moveBlock = (id: string, dir: -1 | 1) => setViewBlocks(viewId, move(blocks, id, dir));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.md, padding: theme.space.sm, maxWidth: 640, width: "100%", margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: theme.space.sm }}>
        <div style={{ fontSize: theme.font.value, color: theme.color.textPrimary }}>{t("customize.views.title")}</div>
        <Focusable
          style={{
            display: "flex", alignItems: "center", justifyContent: "center", gap: theme.space.xs,
            padding: `${theme.space.xs}px ${theme.space.md}px`, borderRadius: theme.radius.sm,
            background: theme.color.accent, color: theme.color.onAccent, fontWeight: 700,
            fontSize: theme.font.body, cursor: "pointer", whiteSpace: "nowrap",
          }}
          aria-label={t("customize.views.done")}
          onActivate={() => closeModal?.()}
          onClick={() => closeModal?.()}
        >
          <LuCheck size={16} /> {t("customize.views.done")}
        </Focusable>
      </div>

      <div style={{ ...theme.card, padding: theme.space.md, display: "flex", flexDirection: "column", gap: theme.space.sm }}>
        <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("customize.views.name")}</span>
        <TextField value={view.name} onChange={(e) => renameView(viewId, e.target.value)} bShowClearAction />
        <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted, marginTop: theme.space.xs }}>{t("customize.views.icon")}</span>
        <div style={{ display: "flex", flexWrap: "wrap", gap: theme.space.sm }}>
          {VIEW_ICON_KEYS.map((key: ViewIconKey) => {
            const on = view.icon === key;
            return (
              <Focusable
                key={key}
                aria-label={key}
                onActivate={() => setViewIcon(viewId, key)}
                onClick={() => setViewIcon(viewId, key)}
                style={{
                  width: 34, height: 34, borderRadius: 9, display: "flex", alignItems: "center", justifyContent: "center",
                  cursor: "pointer",
                  background: on ? `rgba(${theme.color.accentRgb},0.14)` : "rgba(255,255,255,0.06)",
                  color: on ? theme.color.accent : theme.color.textMuted,
                  boxShadow: on ? `inset 0 0 0 1px ${theme.color.accent}` : "none",
                }}
              >
                {viewIconNode(key, 17)}
              </Focusable>
            );
          })}
        </div>
      </div>

      <div style={{ ...theme.card, padding: theme.space.md, display: "flex", flexDirection: "column", gap: theme.space.sm }}>
        <span style={{ fontSize: theme.font.body, color: theme.color.textPrimary }}>{t("customize.views.blocks")}</span>
        {blocks.length === 0 ? (
          <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("customize.views.empty")}</span>
        ) : (
          blocks.map((id, i) => (
            <div key={id} style={{ display: "flex", alignItems: "center", gap: theme.space.sm }}>
              <span style={{ display: "flex", color: theme.color.textMuted }}>{META.get(id)?.icon}</span>
              <span style={{ flex: 1, minWidth: 0, fontSize: theme.font.body, color: theme.color.textPrimary, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label(id)}</span>
              <IconAction label={t("customize.moveUp")} color={i === 0 ? theme.color.textMuted : theme.color.accent} disabled={i === 0} onTap={() => moveBlock(id, -1)}><LuChevronUp size={18} /></IconAction>
              <IconAction label={t("customize.moveDown")} color={i === blocks.length - 1 ? theme.color.textMuted : theme.color.accent} disabled={i === blocks.length - 1} onTap={() => moveBlock(id, 1)}><LuChevronDown size={18} /></IconAction>
              <IconAction label={t("customize.hide")} color={theme.color.danger} onTap={() => removeBlock(id)}><LuX size={18} /></IconAction>
            </div>
          ))
        )}
      </div>

      <div style={{ ...theme.card, padding: theme.space.md, display: "flex", flexDirection: "column", gap: theme.space.sm }}>
        <span style={{ fontSize: theme.font.body, color: theme.color.textPrimary }}>{t("customize.views.add")}</span>
        {CATEGORY_IDS.map((cat) => {
          const meta = TABS.find((x) => x.id === cat)!;
          const avail = pickableIds(cat).filter((id) => !blocks.includes(id) && META.has(id));
          if (avail.length === 0) return null;
          return (
            <Fragment key={cat}>
              <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs, marginTop: theme.space.xs, color: theme.color.textMuted }}>
                {meta.icon}
                <span style={{ fontSize: theme.font.caption }}>{t(meta.labelKey)}</span>
              </div>
              {avail.map((id) => (
                <div key={id} style={{ display: "flex", alignItems: "center", gap: theme.space.sm, paddingLeft: theme.space.md }}>
                  <span style={{ display: "flex", color: theme.color.textMuted }}>{META.get(id)?.icon}</span>
                  <span style={{ flex: 1, minWidth: 0, fontSize: theme.font.body, color: theme.color.textPrimary }}>{label(id)}</span>
                  <IconAction label={t("customize.views.add")} color={theme.color.accent} onTap={() => addBlock(id)}><LuPlus size={18} /></IconAction>
                </div>
              ))}
            </Fragment>
          );
        })}
      </div>

      <ButtonItem
        layout="below"
        onClick={() => {
          if (!confirmDel) { setConfirmDel(true); return; }
          deleteView(viewId);
          closeModal?.();
        }}
      >
        {confirmDel ? t("customize.views.deleteConfirm") : t("customize.views.delete")}
      </ButtonItem>
    </div>
  );
};

const ViewEditorModal: FC<{ viewId: string; closeModal?: () => void }> = ({ viewId, closeModal }) => (
  <ModalRoot closeModal={closeModal} bAllowFullSize>
    <FocusRoot>
      <ViewEditorBody viewId={viewId} closeModal={closeModal} />
    </FocusRoot>
  </ModalRoot>
);

export function openViewEditorModal(viewId: string): void {
  showModal(<ViewEditorModal viewId={viewId} />, window);
}
