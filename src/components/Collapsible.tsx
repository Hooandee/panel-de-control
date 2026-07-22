import { FC, ReactNode, useState } from "react";
import { Focusable, PanelSectionRow } from "@decky/ui";
import { LuChevronDown, LuChevronRight } from "react-icons/lu";

import { theme } from "../theme";
import { isCollapsed, setCollapsed } from "../system/collapseState";

interface Props {
  /** Stable key for persisting this section's collapse state across QAM reopens. */
  id: string;
  icon: ReactNode;
  title: string;
  /** Shown only when collapsed — a one-line at-a-glance summary. */
  summary: ReactNode;
  children: ReactNode;
}

/**
 * A collapsible card: header (icon + title + chevron) always visible; the full
 * content shows when open, a compact summary when closed. Lets the growing
 * control center stay scannable. Collapse state persists per `id` in localStorage
 * (defaults to open). Children render the card's inner content directly
 * (Collapsible owns the card chrome + padding).
 */
export const Collapsible: FC<Props> = ({ id, icon, title, summary, children }) => {
  const [open, setOpen] = useState(() => !isCollapsed(id));
  const toggle = () => {
    const next = !open;
    setOpen(next);
    setCollapsed(id, !next); // persist outside the updater (no side-effect in setState)
  };
  const Chevron = open ? LuChevronDown : LuChevronRight;

  return (
    <PanelSectionRow>
      <div style={{ ...theme.card, padding: theme.space.md, overflow: "hidden" }}>
        <Focusable
          style={{ display: "flex", alignItems: "center", gap: theme.space.sm, cursor: "pointer" }}
          onActivate={toggle}
          onClick={toggle}
        >
          <span style={{ display: "inline-flex", color: theme.color.accent }}>{icon}</span>
          <span style={{ flex: 1, fontSize: theme.font.body, fontWeight: 700, color: theme.color.textPrimary }}>
            {title}
          </span>
          {!open && (
            <span style={{ fontSize: theme.font.caption, color: theme.color.textMuted, whiteSpace: "nowrap" }}>
              {summary}
            </span>
          )}
          <Chevron size={16} color={theme.color.textMuted} />
        </Focusable>
        {open && <div style={{ marginTop: theme.space.sm }}>{children}</div>}
      </div>
    </PanelSectionRow>
  );
};
