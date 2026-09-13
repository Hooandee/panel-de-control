import { FC, ReactNode } from "react";

import { theme } from "../theme";
import { QamAction } from "./QamAction";

export const iconBtn: React.CSSProperties = {
  display: "flex", alignItems: "center", justifyContent: "center",
  padding: 6, borderRadius: theme.radius.sm, cursor: "pointer",
};

export const IconAction: FC<{ label: string; color: string; disabled?: boolean; onTap: () => void; children: ReactNode }> =
  ({ label, color, disabled, onTap, children }) => (
    <QamAction
      onPress={onTap}
      disabled={disabled}
      style={{ ...iconBtn, color, opacity: disabled ? 0.3 : 1, cursor: disabled ? "default" : "pointer" }}
      label={label}
    >
      {children}
    </QamAction>
  );
