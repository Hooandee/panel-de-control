import { FC } from "react";
import { fraction, zoneFor, arcColor, boostWatts, boostEndFraction } from "../tdp/logic";
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

function polarAt(deg: number, r: number): [number, number] {
  const a = (deg * Math.PI) / 180;
  return [CX + r * Math.cos(a), CY + r * Math.sin(a)];
}

function polar(deg: number): [number, number] {
  return polarAt(deg, R);
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

  // Your real TDP (the PL1 you/the loop set). Auto → the setpoint the loop drives
  // (falling back to watts before the first tick); manual → the slider watts.
  // Always known → the big number never shows "—". The base fill, zone, icon and
  // colour all track THIS, not the noisy live draw.
  const tdpWatts = auto ? (setpoint ?? watts) : watts;

  const f = fraction(tdpWatts, limits.min, limits.max_ac);
  const zone = zoneFor(f);
  const color = arcColor(f);
  const ZoneIcon = ZONE_ICON[zone.key];

  // Charger-only headroom: the dim ⚡ segment between the on-battery max and the
  // charger max. NOT the HW boost — this is a fixed ceiling band. (Renamed from
  // the old `hasBoost` to avoid colliding with the real HW-boost segment below.)
  const fMax = fraction(limits.max, limits.min, limits.max_ac);
  const chargerHeadroom = fMax < 1;
  const end = START + SWEEP;
  const fullArc = arcPath(START, end);
  const [sx, sy] = polar(START);
  const [ex, ey] = polar(end);

  // HW boost: the extra watts the chip draws above your TDP via SPPT/FPPT. Null
  // when the draw sensor is down. Only shown when it's a real extra.
  const boost = boostWatts(tdpWatts, actualWatts);
  const hasBoost = boost !== null && boost > 0;
  // Where the boost segment ends on the arc (null → nothing to draw). The clamp to
  // the ceiling and the same-rounded-gate-as-boostWatts live in the pure helper.
  const boostEnd = boostEndFraction(tdpWatts, actualWatts, limits.min, limits.max_ac);

  // White tick at your TDP — the "this is your TDP" marker, in BOTH auto & manual.
  // It sits on the base-fill ↔ boost boundary.
  const tickDeg = START + f * SWEEP;
  const [tx1, ty1] = polarAt(tickDeg, R - SW / 2 - 1);
  const [tx2, ty2] = polarAt(tickDeg, R + SW / 2 + 1);

  return (
    <div style={{ position: "relative", width: "100%", maxWidth: 240, margin: "2px auto 0" }}>
      {/* viewBox cropped to ~180 tall: the 270° arc + its W labels bottom out near
          y172, so the lower ~20px of a square box was dead space that pushed the
          next control away. Overflow stays visible for the round stroke caps. */}
      <svg viewBox="0 0 200 180" style={{ width: "100%", display: "block", overflow: "visible" }}>
        <path d={fullArc} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={SW} strokeLinecap="round" />
        {chargerHeadroom && (
          <path
            d={arcPath(START + fMax * SWEEP, end)}
            fill="none"
            stroke={onAc ? "rgba(255,180,84,0.55)" : "rgba(255,180,84,0.14)"}
            strokeWidth={SW}
            strokeLinecap="round"
            style={{ transition: "stroke 220ms ease" }}
          />
        )}
        {/* Base fill: min → your TDP, coloured by zone. */}
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
        {/* HW boost segment: your TDP → live draw (clamped to arc end), warm + glow. */}
        {boostEnd !== null && (
          <path
            d={arcPath(START + f * SWEEP, START + boostEnd * SWEEP)}
            fill="none"
            stroke={theme.color.boost}
            strokeWidth={SW}
            strokeLinecap="round"
            style={{ filter: `drop-shadow(0 0 7px ${theme.color.boost})` }}
          />
        )}
        {/* Your-TDP tick — the "this is your TDP" marker, in auto and manual. */}
        <line
          x1={tx1}
          y1={ty1}
          x2={tx2}
          y2={ty2}
          stroke="rgba(255,255,255,0.90)"
          strokeWidth={2.5}
          strokeLinecap="round"
        />
        <text x={sx} y={sy + 16} fill={theme.color.textMuted} fontSize="10" textAnchor="middle">{limits.min}W</text>
        <text x={ex} y={ey + 16} fill={theme.color.textMuted} fontSize="10" textAnchor="middle">{limits.max_ac}W{chargerHeadroom ? " ⚡" : ""}</text>
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", pointerEvents: "none" }}>
        {/* Zone icon — hidden in auto mode to make room for AUTO chip */}
        {!auto && <div style={{ lineHeight: 0 }}><ZoneIcon size={26} color={color} /></div>}
        <div style={{ fontSize: 32, fontWeight: 700, color: theme.color.textPrimary, lineHeight: 1.15 }}>
          {Math.round(tdpWatts)}
          {hasBoost && (
            <span style={{ fontSize: 15, fontWeight: 700, color: theme.color.boost, verticalAlign: "super", marginLeft: 1 }}>
              ⁺{boost}
            </span>
          )}
          <span style={{ fontSize: 16, color: theme.color.textMuted }}> W</span>
        </div>
        {hasBoost && (
          <div style={{ fontSize: 9, color: theme.color.boost, marginTop: 1, letterSpacing: "0.04em" }}>
            ⚡ {t("tdp.arc.boostHw")}
          </div>
        )}
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
