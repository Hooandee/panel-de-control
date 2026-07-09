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
  actualWatts?: number | null;
  gpuBusy?: number | null;
  auto?: boolean;
  setpoint?: number | null;
  appliedWatts?: number | null;
}

export const PowerArc: FC<PowerArcProps> = ({
  watts,
  limits,
  onAc,
  actualWatts = null,
  gpuBusy = null,
  auto = false,
  setpoint = null,
  appliedWatts = null,
}) => {
  const { t } = useI18n();

  // The fixed target you set (auto → the loop's setpoint) — shown as a marker.
  const targetWatts = auto ? (setpoint ?? watts) : watts;
  // The live applied PL1 — the hero number + fill. Falls back to the target so it
  // never shows "—".
  const heroWatts = appliedWatts ?? targetWatts;

  const f = fraction(heroWatts, limits.min, limits.max_ac);
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

  // HW boost: watts drawn above the applied PL1 via SPPT/FPPT. Null when no draw
  // sensor; shown only when it's a real extra.
  const boost = boostWatts(heroWatts, actualWatts);
  const hasBoost = boost !== null && boost > 0;
  // Where the boost segment ends on the arc (null → nothing to draw). The clamp to
  // the ceiling and the same-rounded-gate-as-boostWatts live in the pure helper.
  const boostEnd = boostEndFraction(heroWatts, actualWatts, limits.min, limits.max_ac);

  // Marker at the fixed target you set. A small number by it appears only when it
  // diverges from the applied value (eco/HHD/Steam), so it's read, not estimated.
  const fTarget = fraction(targetWatts, limits.min, limits.max_ac);
  const tickDeg = START + fTarget * SWEEP;
  const [tx1, ty1] = polarAt(tickDeg, R - SW / 2 - 1);
  const [tx2, ty2] = polarAt(tickDeg, R + SW / 2 + 1);
  const targetDiverged = Math.round(targetWatts) !== Math.round(heroWatts);
  const [lx, ly] = polarAt(tickDeg, R + SW / 2 + 10);

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
        {/* Base fill: min → applied TDP. A single growing dash (offset 0) so the
            round cap can't bleed a dot onto the far end when f→0. */}
        {f > 0 && (
          <path
            d={fullArc}
            fill="none"
            stroke={color}
            strokeWidth={SW}
            strokeLinecap="round"
            pathLength={1000}
            strokeDasharray={`${1000 * f} 1000`}
            style={{ transition: "stroke-dasharray 240ms ease, stroke 240ms ease", filter: `drop-shadow(0 0 6px ${color})` }}
          />
        )}
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
        {/* Fixed-target tick — where YOU set PL1, in auto and manual. */}
        <line
          x1={tx1}
          y1={ty1}
          x2={tx2}
          y2={ty2}
          stroke="rgba(255,255,255,0.90)"
          strokeWidth={2.5}
          strokeLinecap="round"
        />
        {targetDiverged && (
          <text x={lx} y={ly + 3} fill="rgba(255,255,255,0.90)" fontSize="9" fontWeight={700} textAnchor="middle">
            {Math.round(targetWatts)}W
          </text>
        )}
        <text x={sx} y={sy + 16} fill={theme.color.textMuted} fontSize="10" textAnchor="middle">{limits.min}W</text>
        <text x={ex} y={ey + 16} fill={theme.color.textMuted} fontSize="10" textAnchor="middle">{limits.max_ac}W{chargerHeadroom ? " ⚡" : ""}</text>
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", pointerEvents: "none" }}>
        {/* Zone icon — hidden in auto mode to make room for AUTO chip */}
        {!auto && <div style={{ lineHeight: 0 }}><ZoneIcon size={26} color={color} /></div>}
        <div style={{ fontSize: 32, fontWeight: 700, color: theme.color.textPrimary, lineHeight: 1.15 }}>
          {Math.round(heroWatts)}
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
          <div style={{ fontSize: 10, letterSpacing: "0.14em", textTransform: "uppercase", color }}>{t(`tdp.zone.${zone.key}`)}</div>
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
