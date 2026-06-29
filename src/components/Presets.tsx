import { CSSProperties, FC } from "react";
import { Focusable } from "@decky/ui";
import { TdpLimits } from "../api";
import { theme } from "../theme";

interface PresetsProps {
  limits: TdpLimits;
  onAc: boolean;
  labels: { save: string; balanced: string; turbo: string };
  onPick: (watts: number) => void;
}

export const Presets: FC<PresetsProps> = ({ limits, onAc, labels, onPick }) => {
  const turbo = onAc ? limits.max_ac : limits.max;
  const items = [
    { icon: "😴", label: labels.save, watts: limits.min },
    { icon: "⚖️", label: labels.balanced, watts: limits.default },
    { icon: "🚀", label: labels.turbo, watts: turbo },
  ];
  const btn: CSSProperties = {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: 2,
    padding: "6px 4px",
    borderRadius: theme.radius.sm,
    background: theme.color.surfaceRaised,
    boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
    color: theme.color.textPrimary,
    fontSize: theme.font.caption,
    cursor: "pointer",
  };

  return (
    <Focusable style={{ display: "flex", gap: 6, marginTop: 8 }}>
      {items.map((it) => (
        <Focusable key={it.label} style={btn} onActivate={() => onPick(it.watts)} onClick={() => onPick(it.watts)}>
          <span style={{ fontSize: 16 }}>{it.icon}</span>
          <span>{it.label}</span>
          <span style={{ color: theme.color.textMuted }}>{it.watts}W</span>
        </Focusable>
      ))}
    </Focusable>
  );
};
