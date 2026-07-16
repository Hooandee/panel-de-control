import { CSSProperties, FC } from "react";
import { Focusable } from "@decky/ui";
import { LuCheck, LuPlugZap } from "react-icons/lu";

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

function activeStyle(active: boolean): CSSProperties {
  return active
    ? { ...base, background: theme.color.accent, color: theme.color.onAccent, fontWeight: 600 }
    : { ...base, color: theme.color.textPrimary, boxShadow: `inset 0 0 0 1px ${theme.color.hairline}` };
}

/** A single on/off pill (wrapper / boolean env / single arg). Disabled = tool not
 *  detected: shown dim with an honest note, not focusable. */
export const TogglePill: FC<{
  label: string;
  active: boolean;
  disabled?: boolean;
  disabledNote?: string;
  onToggle: () => void;
}> = ({ label, active, disabled, disabledNote, onToggle }) => {
  if (disabled) {
    return (
      <span
        style={{
          ...base,
          color: theme.color.textMuted,
          opacity: 0.6,
          boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
        }}
      >
        <LuPlugZap size={13} /> {label}
        {disabledNote ? ` · ${disabledNote}` : ""}
      </span>
    );
  }
  return (
    <Focusable style={activeStyle(active)} onActivate={onToggle} onClick={onToggle}>
      {active && <LuCheck size={14} />} {label}
    </Focusable>
  );
};

/** A value pill group: an "Off" chip plus one chip per option (single-choice). */
export const ValuePills: FC<{
  offLabel: string;
  options: { value: string; label: string }[];
  current: string | null;
  onSelect: (value: string | null) => void;
}> = ({ offLabel, options, current, onSelect }) => {
  // A pre-existing value outside our option set (e.g. DXVK_FRAME_RATE=45) is
  // preserved and shown as its own active chip, so the row never reads as "no
  // selection" when a value is actually set.
  const custom = current !== null && !options.some((o) => o.value === current) ? current : null;
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: theme.space.sm }}>
      <Focusable style={activeStyle(current === null)} onActivate={() => onSelect(null)} onClick={() => onSelect(null)}>
        {offLabel}
      </Focusable>
      {options.map((o) => {
        const active = current === o.value;
        return (
          <Focusable
            key={o.value}
            style={activeStyle(active)}
            onActivate={() => onSelect(active ? null : o.value)}
            onClick={() => onSelect(active ? null : o.value)}
          >
            {o.label}
          </Focusable>
        );
      })}
      {custom !== null && (
        <Focusable style={activeStyle(true)} onActivate={() => onSelect(null)} onClick={() => onSelect(null)}>
          {custom}
        </Focusable>
      )}
    </div>
  );
};
