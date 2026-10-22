import { PANEL_H, PANEL_W } from "./pixelFrames";

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Snapped {
  x: number;
  y: number;
  guideX: number | null;
  guideY: number | null;
}

const MAGNET = 2;

/** Positions where a piece clicks into place along one axis, with the edge drawn as a guide. */
function stops(size: number, panel: number, others: { start: number; size: number }[]): { at: number; guide: number }[] {
  const out = [
    { at: 0, guide: 0 },
    { at: panel - size, guide: panel - 1 },
    { at: Math.round((panel - size) / 2), guide: Math.floor(panel / 2) },
  ];
  for (const other of others) {
    const end = other.start + other.size;
    out.push({ at: other.start, guide: other.start }, { at: end, guide: end }, { at: other.start - size, guide: other.start },
      { at: end - size, guide: end - 1 });
  }
  return out;
}

function axis(from: number, delta: number, size: number, panel: number, others: { start: number; size: number }[]) {
  const wanted = from + delta;
  const clamp = (v: number) => Math.max(1 - size, Math.min(panel - 1, v));
  if (delta === 0) return { at: clamp(wanted), guide: null as number | null };
  const ahead = stops(size, panel, others)
    .filter((stop) => (delta > 0 ? stop.at > from : stop.at < from) && Math.abs(stop.at - wanted) <= MAGNET)
    .sort((a, b) => Math.abs(a.at - from) - Math.abs(b.at - from));
  const hit = ahead[0];
  return hit ? { at: clamp(hit.at), guide: hit.guide } : { at: clamp(wanted), guide: null };
}

export function snapMove(boxes: Box[], index: number, dx: number, dy: number): Snapped {
  const box = boxes[index];
  const others = boxes.filter((_, i) => i !== index);
  const x = axis(box.x, dx, box.w, PANEL_W, others.map((o) => ({ start: o.x, size: o.w })));
  const y = axis(box.y, dy, box.h, PANEL_H, others.map((o) => ({ start: o.y, size: o.h })));
  return { x: x.at, y: y.at, guideX: x.guide, guideY: y.guide };
}
