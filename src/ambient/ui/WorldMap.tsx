import { Focusable, GamepadButton } from "@decky/ui";
import { memo, useEffect, useMemo, useRef, useState, type FC, type PointerEvent as ReactPointerEvent, type WheelEvent } from "react";
import { LuMinus, LuPlus } from "react-icons/lu";

import { theme } from "../../theme";
import { STATION_ZOOM, dotRadius, nearestCode, nextPoint, project, stepZoom, viewBoxFor, type Direction, type MapPoint } from "../core/mapNavigation";
import type { RadioCountry, Station } from "../core/types";
import { RoundButton } from "./NowPlaying";
import { WORLD, WORLD_HEIGHT, WORLD_WIDTH } from "./worldMap.data";

export interface MapView {
  zoom: number;
  center: { x: number; y: number };
  nearestCountry: string | null;
}

interface Props {
  countries: readonly RadioCountry[];
  stations: readonly Station[];
  loadingStations: boolean;
  loadingLabel: string;
  selected: string | null;
  playingUrl: string | null;
  playingCountry: string | null;
  onSelect: (code: string | null) => void;
  onPlay: (station: Station) => void;
  onViewChange: (view: MapView) => void;
  zoomInLabel: string;
  zoomOutLabel: string;
}

const DIRECTIONS: Partial<Record<number, Direction>> = {
  [GamepadButton.DIR_UP]: "up",
  [GamepadButton.DIR_DOWN]: "down",
  [GamepadButton.DIR_LEFT]: "left",
  [GamepadButton.DIR_RIGHT]: "right",
};
const DRAG_THRESHOLD_PX = 6;

type PadEvent = { detail: { button: number }; preventDefault(): void; stopPropagation(): void };

const Land = memo(function Land({ highlight }: { highlight: string | null }) {
  return (
    <g>
      {WORLD.map((country) => (
        <path
          key={country.c}
          d={country.d}
          fill={country.c === highlight ? `rgba(${theme.color.accentRgb},0.26)` : "rgba(255,255,255,0.09)"}
          stroke="rgba(255,255,255,0.14)"
          strokeWidth={0.8}
          vectorEffect="non-scaling-stroke"
        />
      ))}
    </g>
  );
});

/**
 * Stations on a flat world. Far out, one dot per country; from 2x, every geolocated station in its
 * city. The d-pad walks between visible dots and leaves at the edges, A plays a focused station,
 * L2/R2 or the wheel zoom, and dragging pans.
 */
export const WorldMap: FC<Props> = ({ countries, stations, loadingStations, loadingLabel, selected, playingUrl, playingCountry, onSelect, onPlay, onViewChange, zoomInLabel, zoomOutLabel }) => {
  const [zoom, setZoom] = useState(1);
  const [center, setCenter] = useState({ x: WORLD_WIDTH / 2, y: WORLD_HEIGHT / 2 });
  /** The view other parts react to; it only moves when the map comes to rest, never mid-drag. */
  const [settled, setSettled] = useState(center);
  const frame = useRef<number | null>(null);
  const pendingCenter = useRef<{ x: number; y: number } | null>(null);
  const [focused, setFocused] = useState<string | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const drag = useRef<{ id: number; x: number; y: number; cx: number; cy: number; moved: boolean } | null>(null);
  const dragged = useRef(false);
  const [pixelWidth, setPixelWidth] = useState(300);

  useEffect(() => {
    const svg = svgRef.current;
    const Observer = svg?.ownerDocument.defaultView?.ResizeObserver;
    if (!svg || !Observer) return;
    const observer = new Observer(([entry]) => {
      if (entry.contentRect.width > 0) setPixelWidth(entry.contentRect.width);
    });
    observer.observe(svg);
    return () => observer.disconnect();
  }, []);

  const countryPoints = useMemo(() => {
    const counts = new Map(countries.map((c) => [c.code, c.count]));
    const max = Math.max(1, ...countries.map((c) => c.count));
    return WORLD.filter((w) => counts.has(w.c)).map((w) => ({ code: w.c, x: w.x, y: w.y, r: dotRadius(counts.get(w.c) ?? 0, max) }));
  }, [countries]);
  const stationPoints = useMemo(() => stations.filter((s) => s.geo).map((s) => ({ code: s.id, station: s, ...project(s.geo![0], s.geo![1]) })), [stations]);

  const stationMode = zoom >= STATION_ZOOM && stationPoints.length > 0;
  const regionLevel = zoom >= STATION_ZOOM;
  const box = viewBoxFor(zoom, center, WORLD_WIDTH, WORLD_HEIGHT);
  /** Map units per screen pixel, so dots and rings keep a real on-screen size at every zoom. */
  const unit = box.width / Math.max(1, pixelWidth);
  const inView = (p: { x: number; y: number }) => p.x >= box.x && p.x <= box.x + box.width && p.y >= box.y && p.y <= box.y + box.height;
  const focusedStation = stationMode ? stationPoints.find((p) => p.code === focused) ?? null : null;

  const moveTo = (next: { x: number; y: number }) => {
    setCenter(next);
    setSettled(next);
  };

  useEffect(() => {
    const country = countryPoints.find((p) => p.code === selected);
    if (country) moveTo({ x: country.x, y: country.y });
  }, [selected, countryPoints]);

  useEffect(() => {
    onViewChange({ zoom, center: settled, nearestCountry: nearestCode(settled, countryPoints) });
  }, [zoom, settled, countryPoints]);

  useEffect(() => () => {
    if (frame.current !== null) cancelAnimationFrame(frame.current);
  }, []);

  const changeZoom = (delta: 1 | -1) => setZoom((z) => stepZoom(z, delta));

  const onDirection = (event: PadEvent) => {
    const direction = DIRECTIONS[event.detail.button];
    if (!direction) return;
    if (stationMode) {
      const visible = stationPoints.filter(inView);
      const from: MapPoint = focusedStation ?? { code: "", x: center.x, y: center.y };
      const next = focusedStation ? nextPoint(from, visible.length > 1 ? visible : stationPoints, direction) : (visible[0] ?? stationPoints[0]).code;
      if (!next) return;
      const point = stationPoints.find((p) => p.code === next)!;
      event.preventDefault();
      event.stopPropagation();
      setFocused(next);
      if (!inView(point)) moveTo({ x: point.x, y: point.y });
      return;
    }
    const current = countryPoints.find((p) => p.code === selected) ?? null;
    const next = current ? nextPoint(current, zoom > 1 ? countryPoints.filter(inView) : countryPoints, direction) : countryPoints[0]?.code ?? null;
    if (!next) return;
    event.preventDefault();
    event.stopPropagation();
    onSelect(next);
  };

  const onButton = (event: PadEvent) => {
    if (event.detail.button === GamepadButton.TRIGGER_RIGHT) changeZoom(1);
    else if (event.detail.button === GamepadButton.TRIGGER_LEFT) changeZoom(-1);
    else return;
    event.preventDefault();
    event.stopPropagation();
  };

  const toMap = (dx: number, dy: number) => {
    const rect = svgRef.current?.getBoundingClientRect();
    const ratio = rect && rect.width > 0 ? box.width / rect.width : 1;
    return { dx: dx * ratio, dy: dy * ratio };
  };
  const onPointerDown = (event: ReactPointerEvent<SVGSVGElement>) => {
    dragged.current = false;
    drag.current = { id: event.pointerId, x: event.clientX, y: event.clientY, cx: center.x, cy: center.y, moved: false };
  };
  const onPointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    const d = drag.current;
    if (!d || d.id !== event.pointerId || zoom === 1) return;
    const moved = Math.hypot(event.clientX - d.x, event.clientY - d.y);
    if (!d.moved && moved < DRAG_THRESHOLD_PX) return;
    if (!d.moved) event.currentTarget.setPointerCapture?.(event.pointerId);
    d.moved = true;
    const { dx, dy } = toMap(event.clientX - d.x, event.clientY - d.y);
    pendingCenter.current = { x: d.cx - dx, y: d.cy - dy };
    frame.current ??= requestAnimationFrame(() => {
      frame.current = null;
      if (pendingCenter.current) setCenter(pendingCenter.current);
    });
  };
  const endDrag = () => {
    const d = drag.current;
    drag.current = null;
    dragged.current = !!d?.moved;
    if (d?.moved) {
      const b = viewBoxFor(zoom, pendingCenter.current ?? center, WORLD_WIDTH, WORLD_HEIGHT);
      pendingCenter.current = null;
      moveTo({ x: b.x + b.width / 2, y: b.y + b.height / 2 });
    }
  };
  const wasDrag = () => dragged.current;
  const onWheel = (event: WheelEvent<SVGSVGElement>) => changeZoom(event.deltaY < 0 ? 1 : -1);

  return (
    <div style={{ position: "relative" }}>
      <Focusable
        onGamepadDirection={onDirection as never}
        onButtonDown={onButton as never}
        onActivate={() => {
          if (focusedStation) onPlay(focusedStation.station);
        }}
        onCancelButton={(focusedStation ? () => setFocused(null) : selected ? () => onSelect(null) : undefined) as never}
        style={{
          borderRadius: theme.radius.md,
          overflow: "hidden",
          background: "rgba(255,255,255,0.03)",
          boxShadow: `inset 0 0 0 1px ${theme.color.hairline}`,
          touchAction: "none",
        }}
      >
        <svg
          ref={svgRef}
          viewBox={`${box.x} ${box.y} ${box.width} ${box.height}`}
          style={{ display: "block", width: "100%", height: "auto", aspectRatio: `${WORLD_WIDTH} / ${WORLD_HEIGHT}`, cursor: zoom > 1 ? "grab" : "default" }}
          role="img"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          onWheel={onWheel}
        >
          <Land highlight={selected} />
          {!stationMode && countryPoints.map((p) => {
            const isSelected = p.code === selected;
            const isPlaying = p.code === playingCountry;
            const r = (1.6 + p.r * 0.45) * Math.max(0.7, 1 / Math.sqrt(zoom)) * unit;
            return (
              <g key={p.code} onClick={() => !wasDrag() && onSelect(isSelected ? null : p.code)} style={{ cursor: "pointer" }}>
                {(isSelected || isPlaying) && <circle cx={p.x} cy={p.y} r={r + 5 * unit} fill={`rgba(${theme.color.accentRgb},0.22)`} />}
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={r}
                  fill={isSelected || isPlaying ? `rgb(${theme.color.accentRgb})` : "rgba(255,255,255,0.6)"}
                  stroke={isSelected ? "#fff" : "rgba(0,0,0,0.35)"}
                  strokeWidth={isSelected ? 1.6 : 0.6}
                  vectorEffect="non-scaling-stroke"
                />
              </g>
            );
          })}
          {stationMode && stationPoints.map((p) => {
            const isFocused = p.code === focused;
            const isPlaying = p.station.url === playingUrl;
            const r = (isFocused ? 5.5 : 3.5) * unit;
            return (
              <g key={p.code} onClick={() => {
                if (wasDrag()) return;
                setFocused(p.code);
                onPlay(p.station);
              }} style={{ cursor: "pointer" }}>
                {(isFocused || isPlaying) && <circle cx={p.x} cy={p.y} r={r + 5 * unit} fill={`rgba(${theme.color.accentRgb},0.25)`} />}
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={r}
                  fill={isFocused || isPlaying ? `rgb(${theme.color.accentRgb})` : "#7ee0a0"}
                  stroke={isFocused ? "#fff" : "rgba(0,0,0,0.45)"}
                  strokeWidth={isFocused ? 1.4 : 0.5}
                  vectorEffect="non-scaling-stroke"
                  opacity={isFocused || isPlaying ? 1 : 0.85}
                />
              </g>
            );
          })}
        </svg>
      </Focusable>
      {regionLevel && loadingStations && (
        <div style={{ position: "absolute", left: 8, bottom: 8, padding: "4px 10px", borderRadius: 99, fontSize: 11, color: "rgba(255,255,255,0.8)", background: "rgba(0,0,0,0.5)", pointerEvents: "none" }}>
          {loadingLabel}
        </div>
      )}
      {focusedStation && (
        <div style={{
          position: "absolute",
          left: 8,
          top: 8,
          maxWidth: "70%",
          padding: "5px 10px",
          borderRadius: 99,
          fontSize: 12,
          fontWeight: 600,
          color: "#fff",
          background: "rgba(0,0,0,0.55)",
          boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.14)",
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          pointerEvents: "none",
        }}>
          {focusedStation.station.name}
        </div>
      )}
      <Focusable flow-children="column" style={{ position: "absolute", right: 8, bottom: 8, display: "flex", flexDirection: "column", gap: 6 }}>
        <RoundButton glass label={zoomInLabel} onActivate={() => changeZoom(1)} size={28}><LuPlus size={14} /></RoundButton>
        <RoundButton glass label={zoomOutLabel} onActivate={() => changeZoom(-1)} size={28}><LuMinus size={14} /></RoundButton>
      </Focusable>
    </div>
  );
};
