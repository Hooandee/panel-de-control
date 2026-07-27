import { FC, ReactNode } from "react";
import { Focusable } from "@decky/ui";

import { theme } from "../theme";

export const iconBtn: React.CSSProperties = {
  display: "flex", alignItems: "center", justifyContent: "center",
  padding: 6, borderRadius: theme.radius.sm, cursor: "pointer",
};

export const IconAction: FC<{ label: string; color: string; disabled?: boolean; onTap: () => void; children: ReactNode }> =
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
