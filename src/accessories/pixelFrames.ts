import type { PixelFrames } from "../api";

export const PANEL_W = 64;
export const PANEL_H = 54;
const MIN_FRAME_MS = 60;

export interface DecodedFrames {
  palette: [number, number, number][];
  frames: Uint8Array[];
  delaysMs: number[];
  firmwareAnimation: number | null;
}

export function decodeFrames(preview: PixelFrames): DecodedFrames {
  const frames = preview.frames.map((b64) => {
    const raw = atob(b64);
    const out = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i += 1) out[i] = raw.charCodeAt(i);
    return out;
  });
  return {
    palette: preview.palette.map((rgb) => [rgb[0] ?? 0, rgb[1] ?? 0, rgb[2] ?? 0]),
    frames,
    delaysMs: preview.delays.map((cs) => Math.max(MIN_FRAME_MS, cs * 10)),
    firmwareAnimation: preview.firmwareAnimation,
  };
}

/** Which frame is on screen `elapsedMs` into a looping animation. */
export function frameAt(delaysMs: number[], elapsedMs: number): number {
  const total = delaysMs.reduce((sum, d) => sum + d, 0);
  if (!total) return 0;
  let t = elapsedMs % total;
  for (let i = 0; i < delaysMs.length; i += 1) {
    if (t < delaysMs[i]) return i;
    t -= delaysMs[i];
  }
  return delaysMs.length - 1;
}
