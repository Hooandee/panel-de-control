import { accessoryEvent, getAccessoriesState } from "../api";
import { readRunningGame } from "../tdp/runningGame";
import { PORTRAIT_W, sendGameInfo } from "./gameInfo";
import { coverCrop, PANEL_H, PANEL_W } from "./pixelFrames";

const POLL_MS = 3000;
const ART_ATTEMPTS = 5;
// The library hero carries no title, so it only stands for the game with its logo on top, as
// Steam's own library shows it; without a logo, the header has the name painted in.
const HERO = "library_hero.jpg";
const LOGO = "logo.png";
const ART_FILES = ["header.jpg", "library_600x900.jpg"];
export const PORTRAIT_FILES = ["library_600x900.jpg", "library_capsule.jpg"];
const LOGO_MAX_W = 0.9;
const LOGO_MAX_H = 0.6;

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(url));
    img.src = url;
  });
}

function encode(ctx: CanvasRenderingContext2D, width: number): string {
  const rgba = ctx.getImageData(0, 0, width, PANEL_H).data;
  let rgb = "";
  for (let i = 0; i < rgba.length; i += 4) rgb += String.fromCharCode(rgba[i], rgba[i + 1], rgba[i + 2]);
  return btoa(rgb);
}

function canvasFor(width: number): CanvasRenderingContext2D | null {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = PANEL_H;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  return ctx;
}

function drawCovered(ctx: CanvasRenderingContext2D, img: HTMLImageElement, width: number) {
  const crop = coverCrop(img.naturalWidth, img.naturalHeight, width, PANEL_H);
  ctx.drawImage(img, crop.sx, crop.sy, crop.sw, crop.sh, 0, 0, width, PANEL_H);
}

/** The logo laid over the hero, fitted inside the panel and centred. */
export function logoBox(logoW: number, logoH: number, width = PANEL_W, height = PANEL_H): { x: number; y: number; w: number; h: number } {
  const scale = Math.min((width * LOGO_MAX_W) / logoW, (height * LOGO_MAX_H) / logoH);
  const w = logoW * scale;
  const h = logoH * scale;
  return { x: (width - w) / 2, y: (height - h) / 2, w, h };
}

async function heroWithLogo(liveAppid: number): Promise<string | null> {
  try {
    const [hero, logo] = await Promise.all([loadImage(`/assets/${liveAppid}/${HERO}`), loadImage(`/assets/${liveAppid}/${LOGO}`)]);
    const ctx = canvasFor(PANEL_W);
    if (!ctx) return null;
    drawCovered(ctx, hero, PANEL_W);
    const box = logoBox(logo.naturalWidth, logo.naturalHeight);
    ctx.drawImage(logo, box.x, box.y, box.w, box.h);
    return encode(ctx, PANEL_W);
  } catch {
    return null;
  }
}

export async function panelPixels(liveAppid: number, files = ART_FILES, width = PANEL_W): Promise<string | null> {
  if (files === ART_FILES) {
    const composed = await heroWithLogo(liveAppid);
    if (composed) return composed;
  }
  for (const file of files) {
    try {
      const img = await loadImage(`/assets/${liveAppid}/${file}`);
      const ctx = canvasFor(width);
      if (!ctx) return null;
      drawCovered(ctx, img, width);
      return encode(ctx, width);
    } catch {
      continue;
    }
  }
  return null;
}

/** Sends the running game's art to the panel scenes; only on the Steam Machine. */
export function startAccessoryArtWatcher(): () => void {
  let alive = true;
  let sent: string | null = null;
  let informed: string | null = null;
  // Art Steam hasn't cached yet is asked for again a few times before giving up for the session.
  const misses = new Map<string, number>();
  let supported: boolean | null = null;
  let busy = false;
  const tick = async () => {
    if (!alive || busy) return;
    busy = true;
    try {
      await step();
    } finally {
      busy = false;
    }
  };
  const step = async () => {
    if (supported === null) {
      try {
        supported = (await getAccessoriesState()).supported;
      } catch {
        return;
      }
    }
    if (!supported) return;
    const game = readRunningGame();
    if (!game || !Number.isFinite(game.liveAppid)) {
      // A relaunch of the same game is a new session: its info and art are sent again.
      sent = null;
      informed = null;
      misses.clear();
      return;
    }
    if (game.appid !== informed) {
      informed = game.appid;
      const portrait = await panelPixels(game.liveAppid, PORTRAIT_FILES, PORTRAIT_W);
      if (!alive) return;
      if (!(await sendGameInfo(game.appid, game.liveAppid, portrait))) informed = null;
    }
    if (game.appid === sent || (misses.get(game.appid) ?? 0) >= ART_ATTEMPTS) return;
    const rgb = await panelPixels(game.liveAppid);
    if (!alive) return;
    if (!rgb) {
      misses.set(game.appid, (misses.get(game.appid) ?? 0) + 1);
      return;
    }
    try {
      if (await accessoryEvent("game_art", { appid: game.appid, rgb })) sent = game.appid;
    } catch {
      /* retried on the next poll */
    }
  };
  const timer = setInterval(() => void tick(), POLL_MS);
  void tick();
  return () => {
    alive = false;
    clearInterval(timer);
  };
}
