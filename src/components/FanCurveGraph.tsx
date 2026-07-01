import { FC, PointerEvent as ReactPointerEvent, memo, useRef, useState } from "react";
import { Point, GEOM, pointsToPath, curveToPx, pxToCurve, clampMonotonic, pwmToPercent } from "../fans/curve";
import { theme } from "../theme";

interface Props {
  points: Point[];
  liveTemp: number | null; // "you are here" marker from the live monitor
  editable: boolean; // only true in custom mode (presets/auto are read-only)
  onChange: (next: Point[]) => void;
  stroke?: string; // curve/point color (default accent); green for a learning preview
  dashed?: boolean; // dashed curve for a not-yet-applied candidate
}

const geom = GEOM;
// Space reserved around the inner plot for the axis labels (left = % labels,
// bottom = °C labels). The inner plot stays geom.width × geom.height.
const MARGIN = { left: 30, top: 10, right: 12, bottom: 22 };

const TEMP_LABELS = [30, 50, 70, 90]; // °C ticks on the X axis
const PERCENT_LABELS = [0, 50, 100]; // fan % gridlines on the Y axis

// Axis positions reuse the shared curve mapping (X = temp at pwm 0); only the
// %-axis Y needs its own helper since percent isn't part of the Point model.
const tempToX = (temp: number) => curveToPx([temp, 0], geom).x;
const percentToY = (percent: number) => geom.height - (percent / 100) * geom.height;

const FanCurveGraphImpl: FC<Props> = ({ points, liveTemp, editable, onChange, stroke, dashed }) => {
  const curveColor = stroke ?? theme.color.accent;
  const svgRef = useRef<SVGSVGElement | null>(null);
  const draggingPoint = useRef<number | null>(null);
  const [activePoint, setActivePoint] = useState<number | null>(null);

  const moveDraggedPoint = (clientX: number, clientY: number) => {
    if (draggingPoint.current === null || !svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    // Map screen px -> svg viewBox px (the svg scales to container width), then
    // strip the left/top margins to get inner-plot coordinates.
    const scaleX = (geom.width + MARGIN.left + MARGIN.right) / rect.width;
    const scaleY = (geom.height + MARGIN.top + MARGIN.bottom) / rect.height;
    const plotX = (clientX - rect.left) * scaleX - MARGIN.left;
    const plotY = (clientY - rect.top) * scaleY - MARGIN.top;
    const dropped = pxToCurve(
      Math.max(0, Math.min(geom.width, plotX)),
      Math.max(0, Math.min(geom.height, plotY)),
      geom,
    );
    const next = points.map((point, i) => (i === draggingPoint.current ? dropped : point));
    onChange(clampMonotonic(next));
  };

  const startDrag = (index: number) => (e: ReactPointerEvent) => {
    if (!editable) return;
    draggingPoint.current = index;
    setActivePoint(index);
    (e.target as Element).setPointerCapture?.(e.pointerId);
  };
  const onPointerMove = (e: ReactPointerEvent) => moveDraggedPoint(e.clientX, e.clientY);
  const endDrag = () => {
    draggingPoint.current = null;
    setActivePoint(null);
  };

  const liveMarkerX =
    liveTemp !== null
      ? tempToX(Math.max(geom.tempMin, Math.min(geom.tempMax, liveTemp)))
      : null;

  const muted = theme.color.textMuted;
  const dragged = activePoint !== null ? points[activePoint] : null;
  const draggedAt = dragged ? curveToPx(dragged, geom) : null;

  return (
    <svg
      ref={svgRef}
      viewBox={`0 0 ${geom.width + MARGIN.left + MARGIN.right} ${geom.height + MARGIN.top + MARGIN.bottom}`}
      style={{ width: "100%", touchAction: "none", opacity: editable ? 1 : 0.55 }}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
    >
      <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
        {/* Y gridlines + % labels */}
        {PERCENT_LABELS.map((percent) => {
          const y = percentToY(percent);
          return (
            <g key={`y${percent}`}>
              <line x1={0} y1={y} x2={geom.width} y2={y} stroke={theme.color.hairline} strokeWidth={1} />
              <text x={-6} y={y + 3} textAnchor="end" fontSize={9} fill={muted}>{percent}</text>
            </g>
          );
        })}
        {/* X ticks + °C labels */}
        {TEMP_LABELS.map((temp) => {
          const x = tempToX(temp);
          return (
            <g key={`x${temp}`}>
              <line x1={x} y1={geom.height} x2={x} y2={geom.height + 3} stroke={muted} strokeWidth={1} />
              <text x={x} y={geom.height + 14} textAnchor="middle" fontSize={9} fill={muted}>{temp}</text>
            </g>
          );
        })}
        {/* axis unit hints */}
        <text x={-6} y={-2} textAnchor="end" fontSize={8} fill={muted}>%</text>
        <text x={geom.width} y={geom.height + 14} textAnchor="end" fontSize={8} fill={muted}>°C</text>

        {/* plot border */}
        <rect x={0} y={0} width={geom.width} height={geom.height} fill="none" stroke={theme.color.hairline} rx={6} />

        {/* the fan curve */}
        <path d={pointsToPath(points, geom)} fill="none" stroke={curveColor} strokeWidth={2} strokeLinejoin="round" strokeDasharray={dashed ? "5 4" : undefined} />

        {/* live "you are here" temperature marker */}
        {liveMarkerX !== null && (
          <>
            <line x1={liveMarkerX} y1={0} x2={liveMarkerX} y2={geom.height} stroke={theme.color.warn} strokeDasharray="3 3" strokeWidth={1} />
            <text x={liveMarkerX} y={-2} textAnchor="middle" fontSize={9} fill={theme.color.warn}>
              {Math.round(liveTemp as number)}°
            </text>
          </>
        )}

        {/* curve points (draggable only in custom mode) */}
        {points.map((point, index) => {
          const { x, y } = curveToPx(point, geom);
          return (
            <circle
              key={index}
              cx={x}
              cy={y}
              r={editable ? 6 : 3}
              fill={curveColor}
              onPointerDown={editable ? startDrag(index) : undefined}
              style={editable ? { cursor: "grab" } : undefined}
            />
          );
        })}

        {/* value readout for the point being dragged */}
        {dragged && draggedAt && (
          <text
            x={Math.min(geom.width - 2, Math.max(0, draggedAt.x))}
            y={Math.max(10, draggedAt.y - 10)}
            textAnchor="middle"
            fontSize={10}
            fill={theme.color.textPrimary}
          >
            {dragged[0]}° · {pwmToPercent(dragged[1])}%
          </text>
        )}
      </g>
    </svg>
  );
};

// The 1.5 s fan monitor poll re-renders the section each tick; memo keeps the
// SVG from rebuilding when the curve/liveTemp props are unchanged (same reason
// Sparkline/FanChip are memoized).
export const FanCurveGraph = memo(FanCurveGraphImpl);
