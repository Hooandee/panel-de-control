import { FC, ReactNode } from "react";
import { Focusable } from "@decky/ui";

import { theme } from "../theme";

interface Props {
  icon: ReactNode;
  tone: string;
  title: string;
  description: string;
  dismissLabel: string;
  onDismiss: () => void;
}

export const NoticeCard: FC<Props> = ({ icon, tone, title, description, dismissLabel, onDismiss }) => (
  <div
    style={{
      ...theme.card,
      padding: theme.space.md,
      marginTop: theme.space.section,
      marginBottom: theme.space.sm,
      overflow: "hidden",
      boxShadow: `inset 0 0 0 1px ${tone}55`,
    }}
  >
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: theme.space.xs,
        fontSize: theme.font.body,
        fontWeight: 700,
        color: tone,
      }}
    >
      {icon} {title}
    </div>
    <div
      style={{
        fontSize: theme.font.caption,
        color: theme.color.textMuted,
        marginTop: theme.space.xs,
        lineHeight: 1.4,
      }}
    >
      {description}
    </div>
    <Focusable
      onActivate={onDismiss}
      onClick={onDismiss}
      noFocusRing
      style={{
        marginTop: theme.space.sm,
        padding: `${theme.space.sm}px ${theme.space.md}px`,
        borderRadius: theme.radius.sm,
        background: theme.color.surface,
        boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
        color: theme.color.textPrimary,
        fontSize: theme.font.body,
        fontWeight: 650,
        textAlign: "center",
      }}
    >
      {dismissLabel}
    </Focusable>
  </div>
);
