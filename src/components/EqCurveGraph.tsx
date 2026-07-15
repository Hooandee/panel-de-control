import { FC, PointerEvent as ReactPointerEvent, memo, useRef, useState } from "react";
import { BAND_FREQS, GAIN_MAX, clampGain, formatHz, gainsToCurvePath } from "../audio/logic";
import { theme } from "../theme";

interface Props {
  gains: number[];
  editable: boolean;
  onChange: (gains: number[]) => void;
  /** Friendly zone labels under the frequency axis (e.g. Graves/Voces/Agudos), each
   *  centered on a band index — so non-audio users know what each region is. */
  zones?: { label: string; band: number }[];
  /** Rotated Y-axis caption (e.g. "− suave · + fuerte") explaining what the dB numbers mean. */
  yTitle?: string;
}

// Inner plot size; margins leave room for the dB labels (left, + Y caption) and the freq
// numbers + zone labels (bottom).
const PLOT = { w: 288, h: 118 };
const MARGIN = { left: 32, top: 10, right: 10, bottom: 34 };
const DB_LABELS = [GAIN_MAX, 0, -GAIN_MAX];

const bandX = (i: number, n: number) => (i / (n - 1)) * PLOT.w;
// Same mapping gainsToCurvePath uses, so a band dot sits exactly on the curve.
const span = (PLOT.h / 2) * 0.85;
const gainToY = (g: number) => PLOT.h / 2 - (clampGain(g) / GAIN_MAX) * span;
const yToGain = (y: number) => clampGain(((PLOT.h / 2 - y) / span) * GAIN_MAX);

const EqCurveGraphImpl: FC<Props> = ({ gains, editable, onChange, zones, yTitle }) => {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const dragging = useRef<number | null>(null);
  const [active, setActive] = useState<number | null>(null);
  const n = gains.length;

  const move = (clientY: number) => {
    if (dragging.current === null || !svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const scaleY = (PLOT.h + MARGIN.top + MARGIN.bottom) / rect.height;
    const plotY = (clientY - rect.top) * scaleY - MARGIN.top;
    const g = Math.round(yToGain(Math.max(0, Math.min(PLOT.h, plotY))));
    const next = gains.map((v, i) => (i === dragging.current ? g : v));
    onChange(next);
  };

  const startDrag = (i: number) => (e: ReactPointerEvent) => {
    if (!editable) return;
    dragging.current = i;
    setActive(i);
    (e.target as Element).setPointerCapture?.(e.pointerId);
  };
  const endDrag = () => {
    dragging.current = null;
    setActive(null);
  };

  const muted = theme.color.textMuted;
  const color = theme.color.accent;

  return (
    <svg
      ref={svgRef}
      viewBox={`0 0 ${PLOT.w + MARGIN.left + MARGIN.right} ${PLOT.h + MARGIN.top + MARGIN.bottom}`}
      style={{ width: "100%", touchAction: "none", opacity: editable ? 1 : 0.6 }}
      onPointerMove={(e) => move(e.clientY)}
      onPointerUp={endDrag}
    >
      <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
        {/* dB gridlines + labels */}
        {DB_LABELS.map((db) => {
          const y = gainToY(db);
          return (
            <g key={`db${db}`}>
              <line x1={0} y1={y} x2={PLOT.w} y2={y} stroke={theme.color.hairline} strokeWidth={1} />
              <text x={-6} y={y + 3} textAnchor="end" fontSize={9} fill={muted}>
                {db > 0 ? `+${db}` : db}
              </text>
            </g>
          );
        })}

        {/* rotated Y-axis caption (what the dB numbers mean) */}
        {yTitle && (
          <text
            transform={`rotate(-90 ${-24} ${PLOT.h / 2})`}
            x={-24}
            y={PLOT.h / 2}
            textAnchor="middle"
            fontSize={8}
            fill={muted}
          >
            {yTitle}
          </text>
        )}

        {/* the EQ response curve */}
        <path
          d={gainsToCurvePath(gains, PLOT.w, PLOT.h)}
          fill="none"
          stroke={color}
          strokeWidth={2}
          strokeLinejoin="round"
        />

        {/* draggable band handles + freq labels */}
        {gains.map((g, i) => {
          const x = bandX(i, n);
          const y = gainToY(g);
          return (
            <g key={i}>
              <circle
                cx={x}
                cy={y}
                r={editable ? 6 : 3}
                fill={color}
                onPointerDown={editable ? startDrag(i) : undefined}
                style={editable ? { cursor: "ns-resize" } : undefined}
              />
              <text x={x} y={PLOT.h + 14} textAnchor="middle" fontSize={8} fill={muted}>
                {formatHz(BAND_FREQS[i])}
              </text>
            </g>
          );
        })}

        {/* friendly zone labels under the frequency numbers */}
        {zones?.map((z) => (
          <text
            key={z.label}
            x={bandX(z.band, n)}
            y={PLOT.h + 27}
            textAnchor="middle"
            fontSize={9}
            fill={theme.color.accent}
          >
            {z.label}
          </text>
        ))}

        {/* value readout for the band being dragged */}
        {active !== null && (
          <text
            x={Math.min(PLOT.w - 2, Math.max(0, bandX(active, n)))}
            y={Math.max(10, gainToY(gains[active]) - 10)}
            textAnchor="middle"
            fontSize={10}
            fill={theme.color.textPrimary}
          >
            {gains[active] > 0 ? `+${gains[active]}` : gains[active]} dB
          </text>
        )}
      </g>
    </svg>
  );
};

export const EqCurveGraph = memo(EqCurveGraphImpl);
