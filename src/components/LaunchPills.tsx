import { CSSProperties, FC } from "react";
import { Focusable } from "@decky/ui";

import { theme } from "../theme";

const base: CSSProperties = {
  fontSize: theme.font.body,
  borderRadius: 20,
  padding: "6px 12px",
  display: "inline-flex",
  alignItems: "center",
  gap: 6,
  cursor: "pointer",
  whiteSpace: "nowrap",
};

function chipStyle(active: boolean): CSSProperties {
  return active
    ? { ...base, background: theme.color.accent, color: theme.color.onAccent, fontWeight: 600 }
    : { ...base, color: theme.color.textPrimary, boxShadow: `inset 0 0 0 1px ${theme.color.hairline}` };
}

/** A single-choice value group: an "Off" chip plus one chip per option. A value
 *  outside the option set (e.g. DXVK_FRAME_RATE=45) shows as its own active chip. */
export const ValuePills: FC<{
  offLabel: string;
  options: { value: string; label: string }[];
  current: string | null;
  onSelect: (value: string | null) => void;
}> = ({ offLabel, options, current, onSelect }) => {
  const custom = current !== null && !options.some((o) => o.value === current) ? current : null;
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: theme.space.sm }}>
      <Focusable style={chipStyle(current === null)} onActivate={() => onSelect(null)} onClick={() => onSelect(null)}>
        {offLabel}
      </Focusable>
      {options.map((o) => {
        const active = current === o.value;
        return (
          <Focusable
            key={o.value}
            style={chipStyle(active)}
            onActivate={() => onSelect(active ? null : o.value)}
            onClick={() => onSelect(active ? null : o.value)}
          >
            {o.label}
          </Focusable>
        );
      })}
      {custom !== null && (
        <Focusable style={chipStyle(true)} onActivate={() => onSelect(null)} onClick={() => onSelect(null)}>
          {custom}
        </Focusable>
      )}
    </div>
  );
};
