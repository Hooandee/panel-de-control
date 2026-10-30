const WIDTH = 320;
const PARALLEL = 2;
const KEEP = 240;

const ready = new Map<string, string>();
const pending = new Map<string, Promise<string | null>>();
const queue: (() => void)[] = [];
let running = 0;

function next(): void {
  while (running < PARALLEL && queue.length) {
    running++;
    queue.shift()!();
  }
}

function remember(url: string, thumb: string): void {
  ready.set(url, thumb);
  while (ready.size > KEEP) {
    const [oldest, objectUrl] = ready.entries().next().value as [string, string];
    ready.delete(oldest);
    URL.revokeObjectURL(objectUrl);
  }
}

async function shrink(url: string): Promise<string | null> {
  const blob = await (await fetch(url)).blob();
  const bitmap = await createImageBitmap(blob, { resizeWidth: WIDTH, resizeQuality: "medium" });
  try {
    const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
    const context = canvas.getContext("2d");
    if (!context) return null;
    context.drawImage(bitmap, 0, 0);
    return URL.createObjectURL(await canvas.convertToBlob({ type: "image/jpeg", quality: 0.82 }));
  } finally {
    bitmap.close();
  }
}

/**
 * A small copy of a picture for library tiles. Photos are decoded straight to tile size, so a
 * folder of 4K images never sits in memory at full resolution; a few at a time, cached.
 */
export function thumbnail(url: string): Promise<string | null> {
  const known = ready.get(url);
  if (known) return Promise.resolve(known);
  const waiting = pending.get(url);
  if (waiting) return waiting;
  const request = new Promise<string | null>((resolve) => {
    queue.push(() => {
      void shrink(url)
        .catch(() => null)
        .then((thumb) => {
          if (thumb) remember(url, thumb);
          resolve(thumb);
        })
        .finally(() => {
          pending.delete(url);
          running--;
          next();
        });
    });
    next();
  });
  pending.set(url, request);
  return request;
}
