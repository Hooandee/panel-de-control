import type { OverlayCorner } from "./types";

export interface Point {
  x: number;
  y: number;
}

export interface Size {
  width: number;
  height: number;
}

export const MARGIN_PX = 16;
export const PILL_WIDTH_PX = 280;

/** Width of the floating card: the mini player alone, or wide enough to hold the video. */
export function cardWidth(viewport: Size, rightInset: number, video: boolean, scalePercent: number): number {
  const free = Math.max(0, viewport.width - rightInset - 2 * MARGIN_PX);
  const wanted = video ? Math.round((viewport.width * scalePercent) / 100) : PILL_WIDTH_PX;
  return Math.min(free, Math.max(PILL_WIDTH_PX, wanted));
}

export function cornerPosition(corner: OverlayCorner, card: Size, viewport: Size, rightInset: number): Point {
  const right = viewport.width - rightInset - MARGIN_PX - card.width;
  const bottom = viewport.height - MARGIN_PX - card.height;
  return {
    x: corner.endsWith("right") ? right : MARGIN_PX,
    y: corner.startsWith("bottom") ? bottom : MARGIN_PX,
  };
}

/** The corner a dropped card settles into: the one its centre is closest to. */
export function nearestCorner(position: Point, card: Size, viewport: Size, rightInset: number): OverlayCorner {
  const cx = position.x + card.width / 2;
  const cy = position.y + card.height / 2;
  const horizontal = cx > (viewport.width - rightInset) / 2 ? "right" : "left";
  const vertical = cy > viewport.height / 2 ? "bottom" : "top";
  return `${vertical}-${horizontal}`;
}

export function clampPosition(position: Point, card: Size, viewport: Size): Point {
  return {
    x: Math.min(Math.max(0, position.x), Math.max(0, viewport.width - card.width)),
    y: Math.min(Math.max(0, position.y), Math.max(0, viewport.height - card.height)),
  };
}

/** One frame of a critically damped approach; returns null once it has arrived. */
export function springStep(current: Point, target: Point, factor = 0.24): Point | null {
  const dx = target.x - current.x;
  const dy = target.y - current.y;
  if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) return null;
  return { x: current.x + dx * factor, y: current.y + dy * factor };
}

export function fullscreenVideoBounds(viewport: Size): Point & Size {
  const width = Math.min(viewport.width, viewport.height * 16 / 9);
  const height = width * 9 / 16;
  return { x: (viewport.width - width) / 2, y: (viewport.height - height) / 2, width, height };
}
