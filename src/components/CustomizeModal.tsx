import { FC, Fragment, ReactNode } from "react";
import { ModalRoot, showModal, Focusable, ButtonItem } from "@decky/ui";
import { LuChevronUp, LuChevronDown, LuEye, LuEyeOff, LuLock, LuCheck } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { TABS, SECTION_BLOCKS, SUBITEMS, blockOrder, PINNED_TAB, ItemMeta } from "../customize/manifest";
import { ListPref, orderIds, move, toggle } from "../customize/layout";
import { useLayout, saveLayout, resetLayout } from "../customize/store";
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

const CustomizeBody: FC = () => {
  const { t } = useI18n();
  const layout = useLayout();

  // One metadata lookup for both tabs and blocks (label via i18n key + icon).
  const metaFor = (items: ItemMeta[] | undefined) => (id: string): RowMeta => {
    const item = items?.find((x) => x.id === id);
    return { id, label: item ? t(item.labelKey) : id, icon: item?.icon };
  };

  // Tabs that expose configurable blocks, in tab order.
  const blockSections = TABS.filter((s) => SECTION_BLOCKS[s.id]?.length);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.lg, padding: theme.space.sm, maxWidth: 720, width: "100%", margin: "0 auto" }}>
      <div style={{ fontSize: theme.font.value, color: theme.color.textPrimary }}>{t("customize.title")}</div>

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

      <ButtonItem layout="below" onClick={() => resetLayout()}>
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
