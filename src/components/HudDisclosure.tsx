import { FC, ReactNode, useState } from "react";
import { LuChevronDown, LuChevronRight } from "react-icons/lu";

import { isCollapsed, setCollapsed } from "../system/collapseState";
import { theme } from "../theme";
import { QamAction } from "./QamAction";

interface Props {
  id: string;
  icon: ReactNode;
  title: string;
  summary: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}

export const HudDisclosure: FC<Props> = ({
  id,
  icon,
  title,
  summary,
  defaultOpen = false,
  children,
}) => {
  const [open, setOpen] = useState(() => !isCollapsed(id, !defaultOpen));
  const toggle = () => {
    const next = !open;
    setOpen(next);
    setCollapsed(id, !next);
  };
  const Chevron = open ? LuChevronDown : LuChevronRight;

  return (
    <div
      style={{
        ...theme.card,
        minWidth: 0,
        padding: theme.space.md,
        overflow: "hidden",
      }}
    >
      <QamAction
        onPress={toggle}
        expanded={open}
        style={{
          display: "flex",
          alignItems: "center",
          gap: theme.space.sm,
          width: "100%",
          minWidth: 0,
          cursor: "pointer",
        }}
      >
        <span style={{ display: "inline-flex", flexShrink: 0, color: theme.color.accent }}>
          {icon}
        </span>
        <span
          style={{
            flex: "0 1 auto",
            minWidth: 0,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            fontSize: theme.font.body,
            fontWeight: 700,
            color: theme.color.textPrimary,
          }}
        >
          {title}
        </span>
        {!open && (
          <span
            style={{
              flex: "1 1 0",
              minWidth: 0,
              maxWidth: "46%",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              textAlign: "right",
              fontSize: theme.font.caption,
              color: theme.color.textMuted,
            }}
          >
            {summary}
          </span>
        )}
        <Chevron size={16} color={theme.color.textMuted} style={{ flexShrink: 0 }} />
      </QamAction>
      {open && <div style={{ marginTop: theme.space.md }}>{children}</div>}
    </div>
  );
};
