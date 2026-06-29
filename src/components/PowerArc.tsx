import { FC } from "react";
import { fraction, zoneFor, arcColor } from "../tdp/logic";
import { ZONE_ICON } from "../tdp/zoneIcons";
import { TdpLimits } from "../api";
import { theme } from "../theme";
import { useI18n } from "../i18n";

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
  actualWatts?: number | null;
  gpuBusy?: number | null;
  auto?: boolean;
  setpoint?: number | null;
}

export const PowerArc: FC<PowerArcProps> = ({
  watts,
  limits,
  onAc,
  zoneLabel,
  actualWatts = null,
  gpuBusy = null,
  auto = false,
  setpoint = null,
}) => {
  const { t } = useI18n();

  // In auto mode the fill tracks real consumption; fall back to manual watts if
  // no live reading is available yet. Never synthesise a value.
  const displayWatts = auto ? (actualWatts ?? watts) : watts;
  const displayAvailable = auto ? actualWatts !== null : true;

  const f = fraction(displayWatts, limits.min, limits.max_ac);
  const zone = zoneFor(f);
  const color = arcColor(f);
  const ZoneIcon = ZONE_ICON[zone.key];
  const fMax = fraction(limits.max, limits.min, limits.max_ac);
  const hasBoost = fMax < 1;
  const end = START + SWEEP;
  const fullArc = arcPath(START, end);
  const [tx, ty] = polar(START + f * SWEEP);
  const [sx, sy] = polar(START);
  const [ex, ey] = polar(end);

  // Setpoint tick (auto mode only): thin radial line inside the arc.
  const setpointFrac =
    auto && setpoint !== null ? fraction(setpoint, limits.min, limits.max_ac) : null;
  const [spx, spy] =
    setpointFrac !== null ? polar(START + setpointFrac * SWEEP) : [0, 0];
  // Inner radius for the tick line
  const rInner = R - SW / 2 - 1;
  const rOuter = R + SW / 2 + 1;
  const getTickPoints = (frac: number): { x1: number; y1: number; x2: number; y2: number } => {
    const deg = START + frac * SWEEP;
    const rad = (deg * Math.PI) / 180;
    return {
      x1: CX + rInner * Math.cos(rad),
      y1: CY + rInner * Math.sin(rad),
      x2: CX + rOuter * Math.cos(rad),
      y2: CY + rOuter * Math.sin(rad),
    };
  };
  const tickPoints = setpointFrac !== null ? getTickPoints(setpointFrac) : null;

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
        {/* Setpoint target marker — shown only in auto mode */}
        {tickPoints !== null && (
          <line
            x1={tickPoints.x1}
            y1={tickPoints.y1}
            x2={tickPoints.x2}
            y2={tickPoints.y2}
            stroke="rgba(255,255,255,0.70)"
            strokeWidth={2}
            strokeLinecap="round"
          />
        )}
        {/* Travelling dot at the fill tip */}
        <circle cx={tx} cy={ty} r={SW / 2 + 1} fill="#fff" style={{ filter: `drop-shadow(0 0 4px ${color})` }} />
        <text x={sx} y={sy + 16} fill={theme.color.textMuted} fontSize="10" textAnchor="middle">{limits.min}W</text>
        <text x={ex} y={ey + 16} fill={theme.color.textMuted} fontSize="10" textAnchor="middle">{limits.max_ac}W{hasBoost ? " ⚡" : ""}</text>
        {/* Setpoint label near the tick */}
        {setpointFrac !== null && setpoint !== null && (
          <text x={spx} y={spy - 6} fill="rgba(255,255,255,0.60)" fontSize="8" textAnchor="middle">{setpoint}W</text>
        )}
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", pointerEvents: "none" }}>
        {/* Zone icon — hidden in auto mode to make room for AUTO chip */}
        {!auto && <div style={{ lineHeight: 0 }}><ZoneIcon size={26} color={color} /></div>}
        <div style={{ fontSize: 32, fontWeight: 700, color: theme.color.textPrimary, lineHeight: 1.15 }}>
          {displayAvailable
            ? <>{Math.round(displayWatts)}<span style={{ fontSize: 16, color: theme.color.textMuted }}> W</span></>
            : <span style={{ fontSize: 24, color: theme.color.textMuted }}>—</span>
          }
        </div>
        {/* AUTO chip — replaces the zone label in auto mode */}
        {auto ? (
          <div style={{
            fontSize: 9,
            fontWeight: 700,
            letterSpacing: "0.14em",
            color: theme.color.accent,
            background: "rgba(78,161,255,0.15)",
            borderRadius: 4,
            padding: "1px 5px",
            marginTop: 2,
          }}>
            {t("tdp.arc.auto")}
          </div>
        ) : (
          <div style={{ fontSize: 10, letterSpacing: "0.14em", textTransform: "uppercase", color }}>{zoneLabel}</div>
        )}
        {/* GPU load — shown in auto mode when data is available */}
        {auto && gpuBusy !== null && (
          <div style={{ fontSize: 9, color: theme.color.textMuted, marginTop: 2 }}>
            {t("tdp.arc.gpu", { pct: Math.round(gpuBusy) })}
          </div>
        )}
      </div>
    </div>
  );
};
