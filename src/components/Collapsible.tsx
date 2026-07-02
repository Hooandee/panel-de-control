import { FC, ReactNode, useState } from "react";
import { Focusable, PanelSectionRow } from "@decky/ui";
import { LuChevronDown, LuChevronRight } from "react-icons/lu";

import { theme } from "../theme";

interface Props {
  icon: ReactNode;
  title: string;
  /** Shown only when collapsed — a one-line at-a-glance summary. */
  summary: ReactNode;
  children: ReactNode;
}

/**
 * A collapsible card: header (icon + title + chevron) always visible; the full
 * content shows when open, a compact summary when closed. Lets the growing
 * control center stay scannable. Starts open; state is in-memory (resets per QAM
 * open) — persisting it is a trivial follow-up. Children render the card's inner
 * content directly (Collapsible owns the card chrome + padding).
 */
export const Collapsible: FC<Props> = ({ icon, title, summary, children }) => {
  const [open, setOpen] = useState(true);
  const Chevron = open ? LuChevronDown : LuChevronRight;

  return (
    <PanelSectionRow>
      <div style={{ ...theme.card, padding: theme.space.md, overflow: "hidden", marginBottom: 6 }}>
        <Focusable
          style={{ display: "flex", alignItems: "center", gap: theme.space.sm, cursor: "pointer" }}
          onActivate={() => setOpen((o) => !o)}
          onClick={() => setOpen((o) => !o)}
        >
          <span style={{ display: "inline-flex", color: theme.color.textPrimary }}>{icon}</span>
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
