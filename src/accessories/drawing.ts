import { PANEL_H, PANEL_W } from "./pixelFrames";

export type Rgb = [number, number, number];

export const DRAW_PALETTE: Rgb[] = [
  [255, 255, 255], [170, 160, 200], [90, 84, 110], [0, 0, 0],
  [255, 70, 90], [255, 140, 50], [255, 214, 70], [140, 240, 110],
  [60, 210, 140], [60, 220, 255], [70, 130, 255], [150, 100, 255],
  [220, 90, 255], [255, 100, 190], [140, 90, 60], [255, 200, 160],
];

export function blankFrame(): Uint8Array {
  return new Uint8Array(PANEL_W * PANEL_H * 3);
}

export function getPixel(frame: Uint8Array, x: number, y: number): Rgb {
  const i = (y * PANEL_W + x) * 3;
  return [frame[i], frame[i + 1], frame[i + 2]];
}

function set(frame: Uint8Array, x: number, y: number, rgb: Rgb): void {
  if (x < 0 || y < 0 || x >= PANEL_W || y >= PANEL_H) return;
  const i = (y * PANEL_W + x) * 3;
  frame[i] = rgb[0];
  frame[i + 1] = rgb[1];
  frame[i + 2] = rgb[2];
}

export function paint(frame: Uint8Array, x: number, y: number, rgb: Rgb, mirror: boolean): void {
  set(frame, x, y, rgb);
  if (mirror) set(frame, PANEL_W - 1 - x, y, rgb);
}

export function fill(frame: Uint8Array, x: number, y: number, rgb: Rgb): void {
  if (x < 0 || y < 0 || x >= PANEL_W || y >= PANEL_H) return;
  const target = getPixel(frame, x, y);
  if (target.every((v, k) => v === rgb[k])) return;
  const stack: [number, number][] = [[x, y]];
  while (stack.length) {
    const [cx, cy] = stack.pop()!;
    if (cx < 0 || cy < 0 || cx >= PANEL_W || cy >= PANEL_H) continue;
    const here = getPixel(frame, cx, cy);
    if (!here.every((v, k) => v === target[k])) continue;
    set(frame, cx, cy, rgb);
    stack.push([cx + 1, cy], [cx - 1, cy], [cx, cy + 1], [cx, cy - 1]);
  }
}

export function encodeFrame(frame: Uint8Array): string {
  let out = "";
  for (let i = 0; i < frame.length; i += 1) out += String.fromCharCode(frame[i]);
  return btoa(out);
}

export function decodeFrame(b64: string): Uint8Array {
  const raw = atob(b64);
  const frame = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) frame[i] = raw.charCodeAt(i);
  return frame;
}
