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
const MIN_AUTO_GAUGE_FRACTION = 0.055;

function autoArcColor(progress: number): string {
  const hue = Math.round(210 + progress * 60);
  return `hsl(${hue}, 82%, 62%)`;
}

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
  auto?: boolean;
  setpoint?: number | null;
  appliedWatts?: number | null;
  visualMax?: number | null;
  baseMarkerWatts?: number | null;
  slowMarkerWatts?: number | null;
  fastMarkerWatts?: number | null;
}

export const PowerArc: FC<PowerArcProps> = ({
  watts,
  limits,
  onAc,
  actualWatts = null,
  auto = false,
  setpoint = null,
  appliedWatts = null,
  visualMax = null,
  baseMarkerWatts = null,
  slowMarkerWatts = null,
  fastMarkerWatts = null,
}) => {
  const { t } = useI18n();

  // Auto owns the dial presentation: firmware rails and readback remain diagnostics,
  // while the player sees the single TDP value maintained by the controller.
  const targetWatts = auto ? (setpoint ?? watts) : watts;
  const heroWatts = auto ? targetWatts : (appliedWatts ?? targetWatts);
  const targetOnly = !auto && appliedWatts === null && (
    baseMarkerWatts !== null || slowMarkerWatts !== null || fastMarkerWatts !== null
  );
  const scaleMax = auto
    ? (onAc ? limits.max_ac : limits.max)
    : Math.max(limits.max_ac, visualMax ?? limits.max_ac);

  const f = fraction(heroWatts, limits.min, scaleMax);
  const gaugeFraction = auto ? Math.max(MIN_AUTO_GAUGE_FRACTION, f) : f;
  const zone = zoneFor(f);
  const color = auto ? autoArcColor(f) : arcColor(f);
  const ZoneIcon = ZONE_ICON[zone.key];

  const fMax = fraction(limits.max, limits.min, scaleMax);
  const fMaxAc = fraction(limits.max_ac, limits.min, scaleMax);
  const chargerHeadroom = !auto && limits.max < limits.max_ac;
  const end = START + SWEEP;
  const fullArc = arcPath(START, end);
  const [sx, sy] = polar(START);
  const [ex, ey] = polar(end);

  // HW boost: watts drawn above the applied PL1 via SPPT/FPPT. Null when no draw
  // sensor; shown only when it's a real extra.
  const boost = auto ? null : boostWatts(heroWatts, actualWatts);
  const hasBoost = boost !== null && boost > 0;
  // Where the boost segment ends on the arc (null → nothing to draw). The clamp to
  // the ceiling and the same-rounded-gate-as-boostWatts live in the pure helper.
  const boostEnd = auto
    ? null
    : boostEndFraction(heroWatts, actualWatts, limits.min, scaleMax);

  // Marker at the fixed target you set. A small number by it appears only when it
  // diverges from the applied value (eco/HHD/Steam), so it's read, not estimated.
  const markerWatts = baseMarkerWatts ?? targetWatts;
  const fTarget = fraction(markerWatts, limits.min, scaleMax);
  const tickDeg = START + fTarget * SWEEP;
  const [tx1, ty1] = polarAt(tickDeg, R - SW / 2 - 1);
  const [tx2, ty2] = polarAt(tickDeg, R + SW / 2 + 1);
  const targetDiverged = Math.round(markerWatts) !== Math.round(heroWatts);
  const showTargetLabel = !auto && (targetDiverged || baseMarkerWatts !== null);
  const targetLabelAtMinimum = showTargetLabel
    && Math.round(markerWatts) === Math.round(limits.min);
  const [lx, ly] = polarAt(tickDeg, R + SW / 2 + 10);
  const slowFraction = slowMarkerWatts === null ? null : fraction(slowMarkerWatts, limits.min, scaleMax);
  const slowDeg = slowFraction === null ? null : START + slowFraction * SWEEP;
  const [slx1, sly1] = slowDeg === null ? [0, 0] : polarAt(slowDeg, R - SW / 2 - 1);
  const [slx2, sly2] = slowDeg === null ? [0, 0] : polarAt(slowDeg, R + SW / 2 + 1);
  const [sllx, slly] = slowDeg === null ? [0, 0] : polarAt(slowDeg, R + SW / 2 + 12);
  const fastFraction = fastMarkerWatts === null ? null : fraction(fastMarkerWatts, limits.min, scaleMax);
  const fastDeg = fastFraction === null ? null : START + fastFraction * SWEEP;
  const [fx1, fy1] = fastDeg === null ? [0, 0] : polarAt(fastDeg, R - SW / 2 - 1);
  const [fx2, fy2] = fastDeg === null ? [0, 0] : polarAt(fastDeg, R + SW / 2 + 1);
  const [flx, fly] = fastDeg === null ? [0, 0] : polarAt(fastDeg, R - SW / 2 - 12);

  return (
    <div style={{ position: "relative", width: "100%", maxWidth: 240, margin: "2px auto 0" }}>
      {/* viewBox cropped to ~180 tall: the 270° arc + its W labels bottom out near
          y172, so the lower ~20px of a square box was dead space that pushed the
          next control away. Overflow stays visible for the round stroke caps. */}
      <svg viewBox="0 0 200 180" style={{ width: "100%", display: "block", overflow: "visible" }}>
        {auto && (
          <path
            data-testid="auto-tdp-halo"
            aria-hidden="true"
            d={fullArc}
            fill="none"
            stroke={color}
            strokeOpacity={0.28}
            strokeWidth={SW + 5}
            strokeLinecap="round"
            pathLength={1000}
            strokeDasharray={`${1000 * gaugeFraction} 1000`}
            style={{ filter: `drop-shadow(0 0 9px ${color})` }}
          />
        )}
        <path d={fullArc} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={SW} strokeLinecap="round" />
        {chargerHeadroom && (
          <path
            d={arcPath(START + fMax * SWEEP, START + fMaxAc * SWEEP)}
            fill="none"
            stroke={onAc ? "rgba(255,180,84,0.55)" : "rgba(255,180,84,0.14)"}
            strokeWidth={SW}
            strokeLinecap="round"
            style={{ transition: "stroke 220ms ease" }}
          />
        )}
        {/* Base fill: min → applied TDP. A single growing dash (offset 0) so the
            round cap can't bleed a dot onto the far end when f→0. */}
        {gaugeFraction > 0 && (
          <path
            data-testid={auto ? "auto-tdp-gauge" : undefined}
            d={fullArc}
            fill="none"
            stroke={color}
            strokeWidth={SW}
            strokeLinecap="round"
            pathLength={1000}
            strokeDasharray={`${1000 * gaugeFraction} 1000`}
            style={{ transition: "stroke-dasharray 240ms ease, stroke 240ms ease", filter: `drop-shadow(0 0 6px ${color})` }}
          />
        )}
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
        {!auto && (
          <line
            x1={tx1}
            y1={ty1}
            x2={tx2}
            y2={ty2}
            stroke="rgba(255,255,255,0.90)"
            strokeWidth={2.5}
            strokeLinecap="round"
          />
        )}
        {showTargetLabel && (
          <text x={lx} y={ly + 3} fill="rgba(255,255,255,0.90)" fontSize="9" fontWeight={700} textAnchor="middle">
            {Math.round(markerWatts)}W
          </text>
        )}
        {!auto && slowMarkerWatts !== null && (
          <>
            <line x1={slx1} y1={sly1} x2={slx2} y2={sly2} stroke={theme.color.accent} strokeWidth={2.5} strokeLinecap="round" />
            <text x={sllx} y={slly + 3} fill={theme.color.accent} fontSize="9" fontWeight={700} textAnchor="middle">
              Slow ≤ {Math.round(slowMarkerWatts)} W
            </text>
          </>
        )}
        {!auto && fastMarkerWatts !== null && (
          <>
            <line x1={fx1} y1={fy1} x2={fx2} y2={fy2} stroke={theme.color.boost} strokeWidth={2.5} strokeLinecap="round" />
            <text x={flx} y={fly + 3} fill={theme.color.boost} fontSize="9" fontWeight={700} textAnchor="middle">
              Fast ≤ {Math.round(fastMarkerWatts)} W
            </text>
          </>
        )}
        {!targetLabelAtMinimum && (
          <text x={sx} y={sy + 16} fill={theme.color.textMuted} fontSize="10" textAnchor="middle">{limits.min}W</text>
        )}
        <text x={ex} y={ey + 16} fill={theme.color.textMuted} fontSize="10" textAnchor="middle">{scaleMax}W{chargerHeadroom ? " ⚡" : ""}</text>
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", pointerEvents: "none" }}>
        {!auto && <div style={{ lineHeight: 0 }}><ZoneIcon size={26} color={color} /></div>}
        <div style={{ fontSize: 32, fontWeight: 700, color: theme.color.textPrimary, lineHeight: 1.15 }}>
          {Math.round(heroWatts)}
          <span style={{ fontSize: 16, color: theme.color.textMuted }}> W</span>
        </div>
        {targetOnly && (
          <div style={{ fontSize: 9, color: theme.color.textMuted, marginTop: 1, letterSpacing: "0.08em" }}>
            {t("tdp.arc.target")}
          </div>
        )}
        {hasBoost && (
          <div style={{ fontSize: 10, color: theme.color.boost, marginTop: 2, letterSpacing: "0.02em", fontWeight: 700 }}>
            +{boost} W · {t("tdp.arc.boostHw")}
          </div>
        )}
        {auto ? (
          <div style={{
            fontSize: 9,
            fontWeight: 700,
            letterSpacing: "0.14em",
            color: theme.color.accent,
            background: `rgba(${theme.color.accentRgb},0.15)`,
            borderRadius: 4,
            padding: "1px 5px",
            marginTop: 2,
          }}>
            {t("tdp.arc.auto")}
          </div>
        ) : (
          <div style={{ fontSize: 10, letterSpacing: "0.14em", textTransform: "uppercase", color }}>{t(`tdp.zone.${zone.key}`)}</div>
        )}
      </div>
    </div>
  );
};
