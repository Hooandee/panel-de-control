export type Direction = "up" | "down" | "left" | "right";

export interface MapPoint {
  code: string;
  x: number;
  y: number;
}

const VECTORS: Record<Direction, [number, number]> = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] };

/**
 * The next point when the d-pad is pressed: the closest one inside a 60° cone of the direction,
 * with points far off the axis penalised so a press feels like "the one over there".
 * Null means nothing lies that way, so focus can leave the map.
 */
export function nextPoint(from: MapPoint, points: readonly MapPoint[], direction: Direction): string | null {
  const [vx, vy] = VECTORS[direction];
  let best: string | null = null;
  let bestScore = Infinity;
  for (const point of points) {
    if (point.code === from.code) continue;
    const dx = point.x - from.x;
    const dy = point.y - from.y;
    const along = dx * vx + dy * vy;
    if (along <= 0) continue;
    const across = Math.abs(dx * vy - dy * vx);
    if (across > along * Math.tan(Math.PI / 3)) continue;
    const score = along + across * 2.2;
    if (score < bestScore) {
      bestScore = score;
      best = point.code;
    }
  }
  return best;
}

/** Dot radius that keeps 3 stations visible and 3000 stations from swallowing Europe. */
export function dotRadius(count: number, max: number): number {
  if (count <= 0 || max <= 0) return 0;
  return 2.2 + 7.8 * (Math.log(count + 1) / Math.log(max + 1));
}

export const ZOOM_LEVELS = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512] as const;
/** From this zoom the map shows each geolocated station in its city instead of one dot per country. */
export const STATION_ZOOM = 8;
/** From this zoom stations come from the area around the view centre instead of the whole country. */
export const CITY_ZOOM = 64;

export interface ViewBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Visible slice of the map for a zoom level, centred on a point and kept inside the world. */
export function viewBoxFor(zoom: number, center: { x: number; y: number }, width: number, height: number): ViewBox {
  const w = width / zoom;
  const h = height / zoom;
  const x = Math.min(Math.max(center.x - w / 2, 0), width - w);
  const y = Math.min(Math.max(center.y - h / 2, 0), height - h);
  return { x, y, width: w, height: h };
}

export function stepZoom(zoom: number, delta: 1 | -1): number {
  const index = ZOOM_LEVELS.indexOf(zoom as (typeof ZOOM_LEVELS)[number]);
  const next = Math.min(ZOOM_LEVELS.length - 1, Math.max(0, (index < 0 ? 0 : index) + delta));
  return ZOOM_LEVELS[next];
}

/** Same equirectangular framing as the bundled world outlines (lat 84..-58 on 1000x500). */
const LAT_TOP = 84;
const LAT_BOTTOM = -58;

export function project(lat: number, lon: number, width = 1000, height = 500): { x: number; y: number } {
  const clamped = Math.min(LAT_TOP, Math.max(LAT_BOTTOM, lat));
  return { x: ((lon + 180) / 360) * width, y: ((LAT_TOP - clamped) / (LAT_TOP - LAT_BOTTOM)) * height };
}

export function nearestCode(center: { x: number; y: number }, points: readonly MapPoint[]): string | null {
  let best: string | null = null;
  let distance = Infinity;
  for (const p of points) {
    const d = (p.x - center.x) ** 2 + (p.y - center.y) ** 2;
    if (d < distance) {
      distance = d;
      best = p.code;
    }
  }
  return best;
}

export function unproject(x: number, y: number, width = 1000, height = 500): { lat: number; lon: number } {
  return { lon: (x / width) * 360 - 180, lat: LAT_TOP - (y / height) * (LAT_TOP - LAT_BOTTOM) };
}

/** Radius in km that covers what the view shows, from its width in map units at a latitude. */
export function viewRadiusKm(viewWidth: number, lat: number, width = 1000): number {
  const degrees = (viewWidth / width) * 360;
  return Math.max(5, (degrees / 2) * 111.32 * Math.max(0.2, Math.cos((lat * Math.PI) / 180)) * 1.2);
}
