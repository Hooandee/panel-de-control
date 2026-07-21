import { FC, Fragment, ReactNode } from "react";
import { ModalRoot, showModal, Focusable, ButtonItem } from "@decky/ui";
import { LuChevronUp, LuChevronDown, LuEye, LuEyeOff, LuLock, LuCheck, LuPower, LuBrain } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { TABS, SECTION_BLOCKS, SUBITEMS, blockOrder, PINNED_TAB, ItemMeta } from "../customize/manifest";
import { ListPref, orderIds, move, toggle } from "../customize/layout";
import { useLayout, saveLayout, resetLayout } from "../customize/store";
import { useModules, setModuleDisabled, resetModules } from "../customize/modules";
import { moduleState, countStates, ModuleState } from "../customize/moduleLogic";
import { FocusRoot } from "./FocusRoot";
import { ACCENTS } from "../system/accentColor";
import { useAccent, setAccent } from "../system/useAccent";

interface RowMeta {
  id: string;
  label: string;
  icon: ReactNode;
}

const iconBtn = (dim: boolean): React.CSSProperties => ({
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  padding: 6,
  borderRadius: theme.radius.sm,
  color: dim ? theme.color.textMuted : theme.color.textPrimary,
  cursor: dim ? "default" : "pointer",
});

/** One row: icon + label + (optional ↑ ↓) and a show/hide (or lock) toggle.
 *  Sub-items pass hideMove — they're fixed in place, only hideable. */
const Row: FC<{
  meta: RowMeta;
  index?: number;
  count?: number;
  hidden: boolean;
  locked: boolean;
  hideMove?: boolean;
  onMove?: (dir: -1 | 1) => void;
  onToggle: () => void;
}> = ({ meta, index = 0, count = 1, hidden, locked, hideMove = false, onMove, onToggle }) => {
  const { t } = useI18n();
  const first = index === 0;
  const last = index === count - 1;
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: theme.space.sm,
        padding: `${theme.space.xs}px ${theme.space.sm}px`,
        ...theme.card,
        borderRadius: theme.radius.sm, // compact rows read better than the card default (md)
        opacity: hidden ? 0.45 : 1,
      }}
    >
      <span style={{ display: "flex", color: theme.color.textMuted }}>{meta.icon}</span>
      <span style={{ flex: 1, minWidth: 0, fontSize: theme.font.body, color: theme.color.textPrimary, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {meta.label}
      </span>
      {!hideMove && (
        <>
          <Focusable style={iconBtn(first)} aria-label={t("customize.moveUp")} onActivate={() => !first && onMove?.(-1)} onClick={() => !first && onMove?.(-1)}>
            <LuChevronUp size={18} style={{ opacity: first ? 0.3 : 1 }} />
          </Focusable>
          <Focusable style={iconBtn(last)} aria-label={t("customize.moveDown")} onActivate={() => !last && onMove?.(1)} onClick={() => !last && onMove?.(1)}>
            <LuChevronDown size={18} style={{ opacity: last ? 0.3 : 1 }} />
          </Focusable>
        </>
      )}
      {locked ? (
        <span style={iconBtn(true)} title={t("customize.locked")}>
          <LuLock size={16} />
        </span>
      ) : (
        <Focusable style={iconBtn(false)} aria-label={hidden ? t("customize.show") : t("customize.hide")} onActivate={onToggle} onClick={onToggle}>
          {hidden ? <LuEyeOff size={18} /> : <LuEye size={18} />}
        </Focusable>
      )}
    </div>
  );
};

/** An editable list (tabs or one section's blocks) driven by a ListPref.
 *  `renderAfter` injects extra content right below a given row — used to nest a
 *  block's hideable sub-items directly under it. */
const ListEditor: FC<{
  title: string;
  defaults: string[];
  metaFor: (id: string) => RowMeta;
  pref: ListPref | undefined;
  pinned?: string[];
  onChange: (next: ListPref) => void;
  renderAfter?: (id: string) => ReactNode;
}> = ({ title, defaults, metaFor, pref, pinned = [], onChange, renderAfter }) => {
  const order = orderIds(defaults, pref?.order);
  const hidden = pref?.hidden ?? [];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
      <div style={theme.sectionLabel}>{title}</div>
      {order.map((id, i) => (
        <Fragment key={id}>
          <Row
            meta={metaFor(id)}
            index={i}
            count={order.length}
            hidden={hidden.includes(id)}
            locked={pinned.includes(id)}
            onMove={(dir) => onChange({ order: move(order, id, dir), hidden })}
            onToggle={() => onChange({ order, hidden: toggle(hidden, id) })}
          />
          {renderAfter?.(id)}
        </Fragment>
      ))}
    </div>
  );
};

/** Hide-only list for the fixed sub-items within one block (no reorder). Nested
 *  under its block's row (indented), so it needs no heading of its own. */
const SubitemEditor: FC<{
  items: ItemMeta[];
  hidden: string[];
  onChange: (next: string[]) => void;
}> = ({ items, hidden, onChange }) => {
  const { t } = useI18n();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs, paddingLeft: theme.space.md }}>
      {items.map((item) => (
        <Row
          key={item.id}
          meta={{ id: item.id, label: t(item.labelKey), icon: item.icon }}
          hidden={hidden.includes(item.id)}
          locked={false}
          hideMove
          onToggle={() => onChange(toggle(hidden, item.id))}
        />
      ))}
    </div>
  );
};

const AccentPicker: FC = () => {
  const { t } = useI18n();
  const active = useAccent();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.sm }}>
      <div style={theme.sectionLabel}>{t("customize.accent")}</div>
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
                width: 34,
                height: 34,
                borderRadius: 999,
                background: a.hex,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                cursor: "pointer",
                boxShadow: on
                  ? `0 0 0 2px ${theme.color.surface}, 0 0 0 4px ${a.hex}`
                  : `inset 0 0 0 1px ${theme.color.hairline}`,
              }}
            >
              {on && <LuCheck size={18} color="#fff" />}
            </Focusable>
          );
        })}
      </div>
    </div>
  );
};

/** The disable-able modules, in display order. Sub-features are indented under
 *  their tab; learning is a global module (no tab). Tabs carry their manifest
 *  icon; sub-features borrow their block icon; learning uses a brain glyph. */
// Tab modules take their label/icon from the manifest TABS (labelKey/icon left
// undefined → resolved below); sub-features and learning carry their own.
interface ModuleDef { id: string; parent?: string; labelKey?: string; icon?: ReactNode; }
const MODULE_ROWS: ModuleDef[] = [
  { id: "power" },
  { id: "autoTdp", parent: "power", labelKey: "tdp.auto.title", icon: SECTION_BLOCKS.power?.find((b) => b.id === "autoTdp")?.icon },
  { id: "system" },
  { id: "display" },
  { id: "fans" },
  { id: "fanControl", parent: "fans", labelKey: "fans.curve.title", icon: SECTION_BLOCKS.fans?.find((b) => b.id === "curve")?.icon },
  { id: "mandos" },
  { id: "learning", labelKey: "settings.telemetry", icon: <LuBrain size={15} /> },
];

/** One module card: icon + name + one-line microcopy (or the blocked reason) +
 *  a state chip + the enable/disable power switch. */
const ModuleRow: FC<{
  label: string;
  desc: string;
  icon: ReactNode;
  state: ModuleState;
  indent: boolean;
  onToggle: () => void;
}> = ({ label, desc, icon, state, indent, onToggle }) => {
  const { t } = useI18n();
  const off = state === "disabled" || state === "blocked";
  const stateLabel =
    state === "background" ? t("customize.state.background")
      : state === "disabled" ? t("customize.state.disabled")
        : state === "blocked" ? t("customize.state.blocked")
          : "";
  return (
    <div
      style={{
        display: "flex", alignItems: "center", gap: theme.space.sm,
        padding: `${theme.space.sm}px ${theme.space.md}px`, ...theme.card,
        marginLeft: indent ? theme.space.lg : 0,
        opacity: off ? 0.5 : 1,
      }}
    >
      <span style={{ display: "flex", color: state === "visible" || state === "background" ? theme.color.accent : theme.color.textMuted }}>{icon}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs }}>
          <span style={{ fontSize: theme.font.body, color: theme.color.textPrimary, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label}</span>
          {stateLabel && (
            <span style={{ fontSize: theme.font.caption, color: state === "background" ? theme.color.accent : theme.color.textMuted }}>· {stateLabel}</span>
          )}
        </div>
        <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{desc}</div>
      </div>
      <Focusable
        style={{ ...iconBtn(false), color: off ? theme.color.textMuted : theme.color.accent }}
        aria-label={off ? t("customize.enable") : t("customize.disable")}
        onActivate={onToggle}
        onClick={onToggle}
      >
        <LuPower size={18} />
      </Focusable>
    </div>
  );
};

/** The enable/disable list — the functional half of the editor (Módulos). */
const ModuleEditor: FC = () => {
  const { t } = useI18n();
  const layout = useLayout();
  const disabled = useModules();
  const tabHidden = (id: string) => (layout.tabs.hidden ?? []).includes(id);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
      <div style={theme.sectionLabel}>{t("customize.modules")}</div>
      {MODULE_ROWS.map((m) => {
        const tab = TABS.find((x) => x.id === m.id);
        const st = moduleState(m.id, disabled, tabHidden(m.id), false);
        const desc = st === "blocked" && m.id === "learning"
          ? t("customize.module.learning.blocked")
          : t(`customize.module.${m.id}.desc`);
        return (
          <ModuleRow
            key={m.id}
            label={t(m.labelKey ?? tab!.labelKey)}
            desc={desc}
            icon={m.icon ?? tab?.icon}
            state={st}
            indent={!!m.parent}
            onToggle={() => setModuleDisabled(m.id, st !== "disabled")}
          />
        );
      })}
    </div>
  );
};

const CustomizeBody: FC = () => {
  const { t } = useI18n();
  const layout = useLayout();
  const disabled = useModules();

  // One metadata lookup for both tabs and blocks (label via i18n key + icon).
  const metaFor = (items: ItemMeta[] | undefined) => (id: string): RowMeta => {
    const item = items?.find((x) => x.id === id);
    return { id, label: item ? t(item.labelKey) : id, icon: item?.icon };
  };

  // Tabs that expose configurable blocks, in tab order.
  const blockSections = TABS.filter((s) => SECTION_BLOCKS[s.id]?.length);

  // Summary over the real tabs (Settings excluded — it's always on). Disabled +
  // blocked both read as "off" for the count.
  const tabHidden = (id: string) => (layout.tabs.hidden ?? []).includes(id);
  const c = countStates(
    TABS.filter((s) => s.id !== PINNED_TAB).map((s) => ({ id: s.id, hidden: tabHidden(s.id) })),
    disabled,
  );
  const summary = t("customize.summary")
    .replace("{on}", String(c.visible))
    .replace("{bg}", String(c.background))
    .replace("{off}", String(c.disabled + c.blocked));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.lg, padding: theme.space.sm, maxWidth: 720, width: "100%", margin: "0 auto" }}>
      <div style={{ fontSize: theme.font.value, color: theme.color.textPrimary }}>{t("customize.title")}</div>
      <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted }}>{summary}</div>

      <ModuleEditor />

      <AccentPicker />

      <ListEditor
        title={t("customize.tabs")}
        defaults={TABS.map((s) => s.id)}
        metaFor={metaFor(TABS)}
        pref={layout.tabs}
        pinned={[PINNED_TAB]}
        onChange={(next) => saveLayout({ ...layout, tabs: next })}
      />

      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.md }}>
        <div style={theme.sectionLabel}>{t("customize.blocks")}</div>
        {blockSections.map((s) => (
          <ListEditor
            key={s.id}
            title={t(s.labelKey)}
            defaults={blockOrder(s.id)}
            metaFor={metaFor(SECTION_BLOCKS[s.id])}
            pref={layout.blocks[s.id]}
            onChange={(next) => saveLayout({ ...layout, blocks: { ...layout.blocks, [s.id]: next } })}
            // A block's hideable sub-items render nested right under its row.
            renderAfter={(bid) =>
              SUBITEMS[bid]?.length ? (
                <SubitemEditor
                  items={SUBITEMS[bid]}
                  hidden={layout.subitems[bid] ?? []}
                  onChange={(next) => saveLayout({ ...layout, subitems: { ...layout.subitems, [bid]: next } })}
                />
              ) : null
            }
          />
        ))}
      </div>

      <ButtonItem layout="below" onClick={() => { resetLayout(); resetModules(); }}>
        {t("customize.reset")}
      </ButtonItem>
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
