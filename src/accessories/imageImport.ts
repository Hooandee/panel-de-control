import { encodeFrame } from "./drawing";
import { coverCrop, PANEL_H, PANEL_W } from "./pixelFrames";

const MAX_FRAMES = 48;

interface DecodedImport {
  frames: string[];
  fps: number;
}

function toFrame(source: CanvasImageSource, width: number, height: number): string {
  const canvas = document.createElement("canvas");
  canvas.width = PANEL_W;
  canvas.height = PANEL_H;
  const ctx = canvas.getContext("2d")!;
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  const crop = coverCrop(width, height);
  ctx.drawImage(source, crop.sx, crop.sy, crop.sw, crop.sh, 0, 0, PANEL_W, PANEL_H);
  const rgba = ctx.getImageData(0, 0, PANEL_W, PANEL_H).data;
  const rgb = new Uint8Array(PANEL_W * PANEL_H * 3);
  for (let i = 0, j = 0; i < rgba.length; i += 4, j += 3) {
    const alpha = rgba[i + 3] / 255;
    rgb[j] = Math.round(rgba[i] * alpha);
    rgb[j + 1] = Math.round(rgba[i + 1] * alpha);
    rgb[j + 2] = Math.round(rgba[i + 2] * alpha);
  }
  return encodeFrame(rgb);
}

interface FrameDecoder {
  tracks: { ready: Promise<void>; selectedTrack?: { frameCount: number } };
  decode(options: { frameIndex: number }): Promise<{ image: VideoFrame & { duration?: number | null; displayWidth: number; displayHeight: number } }>;
}

/** Turns an image file's bytes into panel frames; animated GIFs keep up to 48 frames. */
export async function importImage(mime: string, base64: string): Promise<DecodedImport> {
  const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
  const Decoder = (window as unknown as { ImageDecoder?: new (init: { data: Uint8Array; type: string }) => FrameDecoder }).ImageDecoder;
  if (mime === "image/gif" && Decoder) {
    const decoder = new Decoder({ data: bytes, type: mime });
    await decoder.tracks.ready;
    const count = Math.min(MAX_FRAMES, decoder.tracks.selectedTrack?.frameCount ?? 1);
    const frames: string[] = [];
    let totalMs = 0;
    for (let i = 0; i < count; i += 1) {
      const { image } = await decoder.decode({ frameIndex: i });
      frames.push(toFrame(image, image.displayWidth, image.displayHeight));
      totalMs += (image.duration ?? 100_000) / 1000;
      image.close();
    }
    const fps = Math.max(1, Math.min(30, Math.round(1000 / Math.max(1, totalMs / frames.length))));
    return { frames, fps };
  }
  const url = URL.createObjectURL(new Blob([bytes], { type: mime }));
  try {
    const img = await new Promise<HTMLImageElement>((resolve, reject) => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = () => reject(new Error("decode"));
      image.src = url;
    });
    return { frames: [toFrame(img, img.naturalWidth, img.naturalHeight)], fps: 8 };
  } finally {
    URL.revokeObjectURL(url);
  }
}
