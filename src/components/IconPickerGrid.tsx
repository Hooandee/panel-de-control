import { FC, ReactNode } from "react";
import { Focusable } from "@decky/ui";

import { theme } from "../theme";

interface Props {
  keys: readonly string[];
  value: string;
  renderIcon: (key: string, size: number) => ReactNode;
  onPick: (key: string) => void;
}

/** Selectable icon grid shared by the view editor and the power-preset manager. */
export const IconPickerGrid: FC<Props> = ({ keys, value, renderIcon, onPick }) => (
  <div style={{ display: "flex", flexWrap: "wrap", gap: theme.space.sm }}>
    {keys.map((key) => {
      const on = value === key;
      return (
        <Focusable
          key={key}
          aria-label={key}
          onActivate={() => onPick(key)}
          onClick={() => onPick(key)}
          style={{
            width: 34, height: 34, borderRadius: 9, display: "flex", alignItems: "center",
            justifyContent: "center", cursor: "pointer",
            background: on ? `rgba(${theme.color.accentRgb},0.14)` : "rgba(255,255,255,0.06)",
            color: on ? theme.color.accent : theme.color.textMuted,
            boxShadow: on ? `inset 0 0 0 1px ${theme.color.accent}` : "none",
          }}
        >
          {renderIcon(key, 17)}
        </Focusable>
      );
    })}
  </div>
);
