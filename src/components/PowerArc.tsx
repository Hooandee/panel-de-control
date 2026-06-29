import { FC } from "react";
import { fraction, zoneFor, arcColor } from "../tdp/logic";
import { TdpLimits } from "../api";
import { theme } from "../theme";

const CX = 100;
const CY = 100;
const R = 80;
const SW = 14;
const START = 135;
const SWEEP = 270;

function polar(deg: number): [number, number] {
  const a = (deg * Math.PI) / 180;
  return [CX + R * Math.cos(a), CY + R * Math.sin(a)];
}

function arcPath(startDeg: number, endDeg: number): string {
  const [x1, y1] = polar(startDeg);
  const [x2, y2] = polar(endDeg);
  const large = endDeg - startDeg > 180 ? 1 : 0;
  return `M ${x1.toFixed(2)} ${y1.toFixed(2)} A ${R} ${R} 0 ${large} 1 ${x2.toFixed(2)} ${y2.toFixed(2)}`;
}

interface PowerArcProps {
  watts: number;
  limits: TdpLimits;
  onAc: boolean;
  zoneLabel: string;
}

export const PowerArc: FC<PowerArcProps> = ({ watts, limits, onAc, zoneLabel }) => {
  const f = fraction(watts, limits.min, limits.max_ac);
  const zone = zoneFor(f);
  const color = arcColor(f);
  const fMax = fraction(limits.max, limits.min, limits.max_ac);
  const hasBoost = fMax < 1;
  const end = START + SWEEP;
  const fullArc = arcPath(START, end);
  const [tx, ty] = polar(START + f * SWEEP);
  const [sx, sy] = polar(START);
  const [ex, ey] = polar(end);

  return (
    <div style={{ position: "relative", width: "100%", maxWidth: 240, margin: "6px auto 0" }}>
      <svg viewBox="0 0 200 200" style={{ width: "100%", display: "block", overflow: "visible" }}>
        <path d={fullArc} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={SW} strokeLinecap="round" />
        {hasBoost && (
          <path
            d={arcPath(START + fMax * SWEEP, end)}
            fill="none"
            stroke={onAc ? "rgba(255,180,84,0.55)" : "rgba(255,180,84,0.14)"}
            strokeWidth={SW}
            strokeLinecap="round"
            style={{ transition: "stroke 220ms ease" }}
          />
        )}
        <path
          d={fullArc}
          fill="none"
          stroke={color}
          strokeWidth={SW}
          strokeLinecap="round"
          pathLength={1000}
          strokeDasharray={1000}
          strokeDashoffset={1000 * (1 - f)}
          style={{ transition: "stroke-dashoffset 240ms ease, stroke 240ms ease", filter: `drop-shadow(0 0 6px ${color})` }}
        />
        <circle cx={tx} cy={ty} r={SW / 2 + 1} fill="#fff" style={{ filter: `drop-shadow(0 0 4px ${color})` }} />
        <text x={sx} y={sy + 16} fill={theme.color.textMuted} fontSize="10" textAnchor="middle">{limits.min}W</text>
        <text x={ex} y={ey + 16} fill={theme.color.textMuted} fontSize="10" textAnchor="middle">{limits.max_ac}W{hasBoost ? " ⚡" : ""}</text>
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", pointerEvents: "none" }}>
        <div style={{ fontSize: 26, lineHeight: 1 }}>{zone.icon}</div>
        <div style={{ fontSize: 32, fontWeight: 700, color: theme.color.textPrimary, lineHeight: 1.15 }}>
          {watts}
          <span style={{ fontSize: 16, color: theme.color.textMuted }}> W</span>
        </div>
        <div style={{ fontSize: 10, letterSpacing: "0.14em", textTransform: "uppercase", color }}>{zoneLabel}</div>
      </div>
    </div>
  );
};
