import { FC, Fragment, ReactNode, useEffect, useState } from "react";
import { ModalRoot, showModal, Focusable, ButtonItem } from "@decky/ui";
import { LuChevronUp, LuChevronDown, LuEye, LuEyeOff, LuPower, LuPencil, LuCheck, LuBrain, LuPlus } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { TABS, SECTION_BLOCKS, SUBITEMS, blockOrder, PINNED_TAB } from "../customize/manifest";
import { orderIds, move, toggle, Layout } from "../customize/layout";
import { useLayout, saveLayout, resetLayout } from "../customize/store";
import { useModules, setModuleDisabled, resetModules } from "../customize/modules";
import { moduleState } from "../customize/moduleLogic";
import { FocusRoot } from "./FocusRoot";
import { ACCENTS } from "../system/accentColor";
import { useAccent, setAccent } from "../system/useAccent";
import { getDevice, DeviceInfo } from "../api";
import { sectionHiddenOnDevice, allBlocksHidden } from "../sections/availability";
import { getPresent, usePresentVersion } from "../customize/present";
import { useViews, createView } from "../customize/viewStore";
import { viewIconNode } from "../customize/viewIcons";
import { openViewEditorModal } from "./ViewEditor";

// Blocks that are actually backend MODULES (get the on/off power control) rather
// than cosmetic cards (which get the show/hide eye). Everything else is cosmetic.
const BLOCK_MODULE: Record<string, string> = { autoTdp: "autoTdp", curve: "fanControl" };
// Category ids (tabs minus the pinned Settings), in default order.
const CATEGORY_IDS = TABS.map((t) => t.id).filter((id) => id !== PINNED_TAB);

const iconBtn: React.CSSProperties = {
  display: "flex", alignItems: "center", justifyContent: "center",
  padding: 6, borderRadius: theme.radius.sm, cursor: "pointer",
};
const iconSquare = (on: boolean): React.CSSProperties => ({
  width: 30, height: 30, borderRadius: 9, display: "flex", alignItems: "center", justifyContent: "center",
  background: on ? `rgba(${theme.color.accentRgb},0.14)` : "rgba(255,255,255,0.06)",
  color: on ? theme.color.accent : theme.color.textMuted,
});

/** Small tappable icon (eye / power / arrow). */
const IconAction: FC<{ label: string; color: string; disabled?: boolean; onTap: () => void; children: ReactNode }> =
  ({ label, color, disabled, onTap, children }) => (
    <Focusable
      style={{ ...iconBtn, color, opacity: disabled ? 0.3 : 1, cursor: disabled ? "default" : "pointer" }}
      aria-label={label}
      onActivate={() => !disabled && onTap()}
      onClick={() => !disabled && onTap()}
    >
      {children}
    </Focusable>
  );

/** A row inside an expanded category. Everything can be hidden (eye); rows with
 *  backend machinery (Auto‑TDP, fan control) additionally get an on/off power.
 *  The power column stays reserved (empty) on eye-only rows so they align. */
const ExpansionRow: FC<{
  label: string; icon: ReactNode; indent?: number;
  hidden: boolean; onToggleHide: () => void;
  off?: boolean; onToggleOff?: () => void;
}> = ({ label, icon, indent = 0, hidden, onToggleHide, off, onToggleOff }) => {
  const { t } = useI18n();
  return (
    <div style={{ display: "flex", alignItems: "center", gap: theme.space.sm, paddingLeft: theme.space.sm + indent, opacity: off || hidden ? 0.55 : 1 }}>
      <span style={{ display: "flex", color: theme.color.textMuted }}>{icon}</span>
      <span style={{ flex: 1, minWidth: 0, fontSize: theme.font.body, color: theme.color.textPrimary, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label}</span>
      <IconAction label={hidden ? t("customize.show") : t("customize.hide")} color={theme.color.textMuted} onTap={onToggleHide}>
        {hidden ? <LuEyeOff size={17} /> : <LuEye size={17} />}
      </IconAction>
      {onToggleOff ? (
        <IconAction label={off ? t("customize.enable") : t("customize.disable")} color={off ? theme.color.textMuted : theme.color.accent} onTap={onToggleOff}>
          <LuPower size={17} />
        </IconAction>
      ) : (
        <span style={{ width: 30 }} />
      )}
    </div>
  );
};

const AccentPicker: FC = () => {
  const { t } = useI18n();
  const active = useAccent();
  return (
    <div style={{ ...theme.card, padding: theme.space.md, display: "flex", flexDirection: "column", gap: theme.space.sm }}>
      <span style={{ fontSize: theme.font.body, color: theme.color.textPrimary }}>{t("customize.accent")}</span>
      <div style={{ display: "flex", flexWrap: "wrap", gap: theme.space.sm }}>
        {ACCENTS.map((a) => {
          const on = a.id === active.id;
          return (
            <Focusable
              key={a.id}
              aria-label={t(`accent.${a.id}`)}
              onActivate={() => setAccent(a.id)}
              onClick={() => setAccent(a.id)}
              style={{
                width: 26, height: 26, borderRadius: 999, background: a.hex,
                display: "flex", alignItems: "center", justifyContent: "center", cursor: "pointer",
                boxShadow: on ? `0 0 0 2px ${theme.color.surface}, 0 0 0 4px ${a.hex}` : `inset 0 0 0 1px ${theme.color.hairline}`,
              }}
            >
              {on && <LuCheck size={15} color="#fff" />}
            </Focusable>
          );
        })}
      </div>
    </div>
  );
};

const CustomizeBody: FC = () => {
  const { t } = useI18n();
  const layout = useLayout();
  const disabled = useModules();
  useAccent(); // re-render the whole modal live when the accent changes (separate root)
  usePresentVersion(); // reflect which blocks each machine actually has
  const [editing, setEditing] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  // Device (one-time) so we don't list a category this machine can't use (e.g.
  // Mandos on the Steam Deck) — mirrors the shell's tab gating.
  const [device, setDevice] = useState<DeviceInfo | null>(null);
  useEffect(() => { getDevice().then(setDevice).catch(() => {}); }, []);

  const catOrder = orderIds(CATEGORY_IDS, layout.tabs.order)
    .filter((id) => CATEGORY_IDS.includes(id) && !sectionHiddenOnDevice(device, id));
  const tabHidden = (id: string) => (layout.tabs.hidden ?? []).includes(id);

  const save = (next: Layout) => saveLayout(next);
  const setTabHidden = (id: string) =>
    save({ ...layout, tabs: { order: layout.tabs.order ?? [], hidden: toggle(layout.tabs.hidden ?? [], id) } });
  // Show a category again: clear its own hide AND un-hide all its children (a tab
  // hidden only because every child was hidden comes back when we restore them).
  const showCategory = (id: string) => {
    const pref = layout.blocks[id] ?? { order: [], hidden: [] };
    save({
      ...layout,
      tabs: { order: layout.tabs.order ?? [], hidden: (layout.tabs.hidden ?? []).filter((x) => x !== id) },
      blocks: { ...layout.blocks, [id]: { ...pref, hidden: [] } },
    });
  };
  const moveCat = (id: string, dir: -1 | 1) => {
    const next = move(catOrder, id, dir);
    // Settings stays pinned last; persist the reordered categories + it.
    save({ ...layout, tabs: { ...layout.tabs, order: [...next, PINNED_TAB] } });
  };
  const setBlockHidden = (cat: string, block: string) => {
    const pref = layout.blocks[cat] ?? { order: [], hidden: [] };
    save({ ...layout, blocks: { ...layout.blocks, [cat]: { ...pref, hidden: toggle(pref.hidden ?? [], block) } } });
  };
  const setSubitemHidden = (block: string, sub: string) =>
    save({ ...layout, subitems: { ...layout.subitems, [block]: toggle(layout.subitems[block] ?? [], sub) } });

  const catMeta = (id: string) => TABS.find((x) => x.id === id)!;
  const learningState = moduleState("learning", disabled, false, false);
  const views = useViews();

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.md, padding: theme.space.sm, maxWidth: 640, width: "100%", margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ fontSize: theme.font.value, color: theme.color.textPrimary }}>{t("customize.title")}</div>
        <Focusable
          style={{
            ...iconBtn, gap: theme.space.xs, padding: `${theme.space.xs}px ${theme.space.sm}px`,
            fontSize: theme.font.caption,
            color: editing ? theme.color.accent : theme.color.textMuted,
            boxShadow: `inset 0 0 0 1px ${editing ? theme.color.accent : theme.color.hairline}`,
            background: editing ? `rgba(${theme.color.accentRgb},0.14)` : "transparent",
          }}
          aria-label={t("customize.reorder")}
          onActivate={() => { setEditing((v) => !v); setOpenId(null); }}
          onClick={() => { setEditing((v) => !v); setOpenId(null); }}
        >
          {editing ? <LuCheck size={15} /> : <LuPencil size={15} />}
          <span>{editing ? t("customize.reorder.done") : t("customize.reorder")}</span>
        </Focusable>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
        {catOrder.map((id, i) => {
          const meta = catMeta(id);
          const present = getPresent(id);
          const off = disabled.has(id);
          // Effective hidden = the tab won't show: user hid it, or every block it
          // has on this machine is hidden. Reflected on the parent's eye so it
          // doesn't read "visible" while the tab is gone.
          const hidden = !off && (tabHidden(id) || allBlocksHidden(id, layout.blocks, present));
          // Only the blocks this machine actually renders (fallback: manifest).
          const manifestBlocks = SECTION_BLOCKS[id] ?? [];
          const blocks = present ? manifestBlocks.filter((b) => present.includes(b.id)) : manifestBlocks;
          const expandable = blocks.length > 0 && !off && !editing;
          const open = openId === id && expandable;
          const stateNote = off ? t("customize.state.disabled") : hidden ? t("customize.state.background") : "";
          return (
            <div key={id} style={{ ...theme.card, padding: `${theme.space.sm + 2}px ${theme.space.md}px`, opacity: off ? 0.5 : 1 }}>
              <div style={{ display: "flex", alignItems: "center", gap: theme.space.sm }}>
                <Focusable
                  style={{ display: "flex", alignItems: "center", gap: theme.space.sm, flex: 1, minWidth: 0, cursor: expandable ? "pointer" : "default" }}
                  aria-label={meta ? t(meta.labelKey) : id}
                  onActivate={() => expandable && setOpenId(open ? null : id)}
                  onClick={() => expandable && setOpenId(open ? null : id)}
                >
                  <span style={iconSquare(!off)}>{meta?.icon}</span>
                  <span style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
                    <span style={{ fontSize: theme.font.body, color: theme.color.textPrimary, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {t(meta.labelKey)}
                      {stateNote && <span style={{ color: theme.color.textMuted, fontSize: theme.font.caption }}> · {stateNote}</span>}
                    </span>
                  </span>
                </Focusable>

                {editing ? (
                  <>
                    <IconAction label={t("customize.moveUp")} color={i === 0 ? theme.color.textMuted : theme.color.accent} disabled={i === 0} onTap={() => moveCat(id, -1)}>
                      <LuChevronUp size={18} />
                    </IconAction>
                    <IconAction label={t("customize.moveDown")} color={i === catOrder.length - 1 ? theme.color.textMuted : theme.color.accent} disabled={i === catOrder.length - 1} onTap={() => moveCat(id, 1)}>
                      <LuChevronDown size={18} />
                    </IconAction>
                  </>
                ) : (
                  <>
                    {/* Fixed eye slot: empty when off (nothing to hide) so the power
                        column stays aligned with enabled rows. */}
                    <span style={{ display: "flex", justifyContent: "center", width: 30 }}>
                      {!off && (
                        <IconAction label={hidden ? t("customize.show") : t("customize.hide")} color={theme.color.textMuted} onTap={() => (hidden ? showCategory(id) : setTabHidden(id))}>
                          {hidden ? <LuEyeOff size={18} /> : <LuEye size={18} />}
                        </IconAction>
                      )}
                    </span>
                    <IconAction label={off ? t("customize.enable") : t("customize.disable")} color={off ? theme.color.textMuted : theme.color.accent} onTap={() => setModuleDisabled(id, !off)}>
                      <LuPower size={18} />
                    </IconAction>
                    {/* Fixed chevron slot so eye/power stay aligned across rows. When
                        expandable it's tappable too (the chevron looks like a button). */}
                    {expandable ? (
                      <IconAction label={t(meta.labelKey)} color={theme.color.textMuted} onTap={() => setOpenId(open ? null : id)}>
                        {open ? <LuChevronUp size={17} /> : <LuChevronDown size={17} />}
                      </IconAction>
                    ) : (
                      <span style={{ display: "flex", justifyContent: "center", width: 30 }} />
                    )}
                  </>
                )}
              </div>

              {open && (
                <div style={{ marginTop: theme.space.sm, paddingTop: theme.space.sm, borderTop: `1px solid ${theme.color.hairline}`, display: "flex", flexDirection: "column", gap: theme.space.sm }}>
                  {orderIds(blockOrder(id), layout.blocks[id]?.order).map((bid) => {
                    const b = blocks.find((x) => x.id === bid);
                    if (!b) return null;
                    const modId = BLOCK_MODULE[bid];
                    const bHidden = (layout.blocks[id]?.hidden ?? []).includes(bid);
                    const mOff = modId ? moduleState(modId, disabled, false, false) === "disabled" : undefined;
                    return (
                      <Fragment key={bid}>
                        <ExpansionRow
                          label={t(b.labelKey)}
                          icon={b.icon}
                          hidden={bHidden}
                          onToggleHide={() => setBlockHidden(id, bid)}
                          off={mOff}
                          onToggleOff={modId ? () => setModuleDisabled(modId, !mOff) : undefined}
                        />
                        {(SUBITEMS[bid] ?? []).map((s) => (
                          <ExpansionRow key={s.id} label={t(s.labelKey)} icon={s.icon} indent={theme.space.lg} hidden={(layout.subitems[bid] ?? []).includes(s.id)} onToggleHide={() => setSubitemHidden(bid, s.id)} />
                        ))}
                      </Fragment>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}

        {/* Learning is a global module (no category) — a plain on/off row. */}
        {!editing && (
          <div style={{ ...theme.card, padding: `${theme.space.sm + 2}px ${theme.space.md}px`, opacity: learningState === "disabled" || learningState === "blocked" ? 0.5 : 1 }}>
            <div style={{ display: "flex", alignItems: "center", gap: theme.space.sm }}>
              <span style={iconSquare(learningState === "visible")}><LuBrain size={16} /></span>
              <span style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
                <span style={{ fontSize: theme.font.body, color: theme.color.textPrimary }}>{t("settings.telemetry")}</span>
                <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>
                  {learningState === "blocked" ? t("customize.module.learning.blocked") : t("customize.module.learning.desc")}
                </span>
              </span>
              {/* Empty eye slot so the power lands in the same column as the categories. */}
              <span style={{ width: 30 }} />
              <IconAction
                label={learningState === "disabled" ? t("customize.enable") : t("customize.disable")}
                color={learningState === "visible" ? theme.color.accent : theme.color.textMuted}
                disabled={learningState === "blocked"}
                onTap={() => setModuleDisabled("learning", learningState !== "disabled")}
              >
                <LuPower size={18} />
              </IconAction>
              <span style={{ width: 30 }} />{/* empty chevron slot */}
            </div>
          </div>
        )}
      </div>

      {!editing && (
        <>
          <div style={theme.sectionLabel}>{t("customize.views.title")}</div>
          <div style={{ ...theme.card, padding: theme.space.md, display: "flex", flexDirection: "column", gap: theme.space.sm }}>
            {views.length === 0 ? (
              <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{t("customize.views.none")}</span>
            ) : (
              views.map((v) => (
                <Focusable
                  key={v.id}
                  style={{ display: "flex", alignItems: "center", gap: theme.space.sm, cursor: "pointer" }}
                  aria-label={v.name}
                  onActivate={() => openViewEditorModal(v.id)}
                  onClick={() => openViewEditorModal(v.id)}
                >
                  <span style={iconSquare(true)}>{viewIconNode(v.icon, 16)}</span>
                  <span style={{ flex: 1, minWidth: 0, fontSize: theme.font.body, color: theme.color.textPrimary, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {v.name || t("customize.views.namePlaceholder")}
                  </span>
                  <LuPencil size={16} color={theme.color.textMuted} />
                </Focusable>
              ))
            )}
            <Focusable
              style={{ ...iconBtn, gap: theme.space.xs, justifyContent: "center", padding: `${theme.space.sm}px`, color: theme.color.accent, boxShadow: `inset 0 0 0 1px ${theme.color.hairline}` }}
              aria-label={t("customize.views.new")}
              onActivate={() => openViewEditorModal(createView(""))}
              onClick={() => openViewEditorModal(createView(""))}
            >
              <LuPlus size={16} /> <span style={{ fontSize: theme.font.body }}>{t("customize.views.new")}</span>
            </Focusable>
          </div>

          <div style={theme.sectionLabel}>{t("customize.appearance")}</div>
          <AccentPicker />
          <ButtonItem layout="below" onClick={() => { resetLayout(); resetModules(); }}>
            {t("customize.reset")}
          </ButtonItem>
        </>
      )}
    </div>
  );
};

const CustomizeModal: FC<{ closeModal?: () => void }> = ({ closeModal }) => (
  <ModalRoot closeModal={closeModal} bAllowFullSize>
    <FocusRoot>
      <CustomizeBody />
    </FocusRoot>
  </ModalRoot>
);

/** Open the full-screen customization editor. Saves are live (module store),
 *  so the shell/sections update behind the modal with no onClose plumbing. */
export function openCustomizeModal(): void {
  showModal(<CustomizeModal />, window);
}
