import type { VideoQuality } from "./types";

export interface VideoTarget {
  height: number;
  fps: number;
}

const LIGHT_FRACTION = 0.25;
const MIN_HEIGHT = 144;

/**
 * Steam's browser decodes video without the GPU and repaints on every frame. Under a quarter of
 * the screen height the size barely matters any more, so the light levels keep motion fluid and
 * only the sharp level pays for full resolution.
 */
export function videoTarget(quality: VideoQuality, screenHeight: number): VideoTarget {
  if (quality === "sharp") return { height: screenHeight, fps: 30 };
  const height = Math.max(MIN_HEIGHT, Math.round((screenHeight * LIGHT_FRACTION) / 2) * 2);
  return { height, fps: quality === "saver" ? 15 : 30 };
}

/** Sharp only resizes oversized videos; the light levels copy every video once. */
export function needsCopy(quality: VideoQuality, videoHeight: number, target: VideoTarget): boolean {
  return quality !== "sharp" || videoHeight > target.height * 1.2;
}
