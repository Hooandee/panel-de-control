import { FC, ReactNode } from "react";

import { theme } from "../theme";

export const ExperimentalBadge: FC<{ children: ReactNode }> = ({ children }) => (
  <span
    data-pdc-experimental-badge="true"
    style={{
      alignSelf: "flex-start",
      boxSizing: "border-box",
      flexShrink: 0,
      fontSize: 9,
      lineHeight: 1.2,
      padding: "2px 5px",
      borderRadius: 999,
      color: theme.color.warn,
      boxShadow: `inset 0 0 0 1px ${theme.color.warn}`,
      whiteSpace: "nowrap",
    }}
  >
    {children}
  </span>
);

interface ExperimentalLabelProps {
  badge: ReactNode;
  title: ReactNode;
}

export const ExperimentalLabel: FC<ExperimentalLabelProps> = ({ badge, title }) => (
  <span
    style={{
      display: "inline-flex",
      flexDirection: "column",
      alignItems: "flex-start",
      gap: 4,
    }}
  >
    <ExperimentalBadge>{badge}</ExperimentalBadge>
    <span>{title}</span>
  </span>
);
