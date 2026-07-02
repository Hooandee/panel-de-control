import { FC, ReactNode } from "react";
import { ModalRoot, showModal, Focusable, ButtonItem } from "@decky/ui";
import { LuChevronUp, LuChevronDown, LuEye, LuEyeOff, LuLock } from "react-icons/lu";

import { useI18n } from "../i18n";
import { theme } from "../theme";
import { TABS, SECTION_BLOCKS, blockOrder, PINNED_TAB, ItemMeta } from "../customize/manifest";
import { ListPref, orderIds, move, toggle } from "../customize/layout";
import { useLayout, saveLayout, resetLayout } from "../customize/store";

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

/** One reorderable row: icon + label + ↑ ↓ and a show/hide (or lock) toggle. */
const Row: FC<{
  meta: RowMeta;
  index: number;
  count: number;
  hidden: boolean;
  locked: boolean;
  onMove: (dir: -1 | 1) => void;
  onToggle: () => void;
}> = ({ meta, index, count, hidden, locked, onMove, onToggle }) => {
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
      <Focusable style={iconBtn(first)} aria-label={t("customize.moveUp")} onActivate={() => !first && onMove(-1)} onClick={() => !first && onMove(-1)}>
        <LuChevronUp size={18} style={{ opacity: first ? 0.3 : 1 }} />
      </Focusable>
      <Focusable style={iconBtn(last)} aria-label={t("customize.moveDown")} onActivate={() => !last && onMove(1)} onClick={() => !last && onMove(1)}>
        <LuChevronDown size={18} style={{ opacity: last ? 0.3 : 1 }} />
      </Focusable>
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

/** An editable list (tabs or one section's blocks) driven by a ListPref. */
const ListEditor: FC<{
  title: string;
  defaults: string[];
  metaFor: (id: string) => RowMeta;
  pref: ListPref | undefined;
  pinned?: string[];
  onChange: (next: ListPref) => void;
}> = ({ title, defaults, metaFor, pref, pinned = [], onChange }) => {
  const order = orderIds(defaults, pref?.order);
  const hidden = pref?.hidden ?? [];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
      <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, textTransform: "uppercase", letterSpacing: 0.5 }}>{title}</div>
      {order.map((id, i) => (
        <Row
          key={id}
          meta={metaFor(id)}
          index={i}
          count={order.length}
          hidden={hidden.includes(id)}
          locked={pinned.includes(id)}
          onMove={(dir) => onChange({ order: move(order, id, dir), hidden })}
          onToggle={() => onChange({ order, hidden: toggle(hidden, id) })}
        />
      ))}
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

      <ListEditor
        title={t("customize.tabs")}
        defaults={TABS.map((s) => s.id)}
        metaFor={metaFor(TABS)}
        pref={layout.tabs}
        pinned={[PINNED_TAB]}
        onChange={(next) => saveLayout({ ...layout, tabs: next })}
      />

      <div style={{ display: "flex", flexDirection: "column", gap: theme.space.md }}>
        <div style={{ fontSize: theme.font.caption, color: theme.color.textMuted, textTransform: "uppercase", letterSpacing: 0.5 }}>{t("customize.blocks")}</div>
        {blockSections.map((s) => (
          <ListEditor
            key={s.id}
            title={t(s.labelKey)}
            defaults={blockOrder(s.id)}
            metaFor={metaFor(SECTION_BLOCKS[s.id])}
            pref={layout.blocks[s.id]}
            onChange={(next) => saveLayout({ ...layout, blocks: { ...layout.blocks, [s.id]: next } })}
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
    <CustomizeBody />
  </ModalRoot>
);

/** Open the full-screen customization editor. Saves are live (module store),
 *  so the shell/sections update behind the modal with no onClose plumbing. */
export function openCustomizeModal(): void {
  showModal(<CustomizeModal />, window);
}
