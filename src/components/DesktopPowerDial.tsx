import { FC } from "react";

import { dialFraction } from "../desktop/presentation";
import { theme } from "../theme";

const SIZE = 124;
const STROKE = 8;

interface Props {
  value: number | null;
  min: number | null;
  max: number | null;
  label: string;
  unavailable: string;
}

export const DesktopPowerDial: FC<Props> = ({ value, min, max, label, unavailable }) => {
  const radius = (SIZE - STROKE) / 2;
  const circumference = 2 * Math.PI * radius;
  const fraction = dialFraction(value, min, max);
  const display = value == null ? unavailable : `${Math.round(value)}`;
  const accessible = value == null ? `${label}: ${unavailable}` : `${label}: ${Math.round(value)} W`;

  return (
    <div role="img" aria-label={accessible} style={{ width: SIZE, height: SIZE, position: "relative", flexShrink: 0 }}>
      <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} aria-hidden="true">
        <circle cx={SIZE / 2} cy={SIZE / 2} r={radius} fill="rgba(0,0,0,0.16)"
          stroke={theme.color.hairline} strokeWidth={STROKE} />
        <circle cx={SIZE / 2} cy={SIZE / 2} r={radius} fill="none"
          stroke={theme.color.accent} strokeWidth={STROKE}
          strokeDasharray={`${circumference * fraction} ${circumference}`}
          strokeLinecap="round" transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}
          style={{ filter: `drop-shadow(0 0 5px rgba(${theme.color.accentRgb},0.24))` }} />
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", textAlign: "center", padding: 18 }}>
        <div data-testid="desktop-power-dial-value" style={{ display: "flex", alignItems: "baseline", gap: 3, maxWidth: "100%" }}>
          <span style={{ maxWidth: "100%", fontSize: value == null ? theme.font.caption : 31, fontWeight: 750, lineHeight: 1, letterSpacing: value == null ? 0 : "-0.05em", color: theme.color.textPrimary, fontVariantNumeric: "tabular-nums", whiteSpace: value == null ? "normal" : "nowrap" }}>
            {display}
          </span>
          {value != null && <span style={{ fontSize: 10, fontWeight: 600, color: theme.color.textMuted }}>W</span>}
        </div>
      </div>
    </div>
  );
};
