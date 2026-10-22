import { accessoryEvent, getAccessoriesState } from "../api";
import { readRunningGame } from "../tdp/runningGame";
import { PORTRAIT_W, sendGameInfo } from "./gameInfo";
import { coverCrop, PANEL_H, PANEL_W } from "./pixelFrames";

const POLL_MS = 3000;
const ART_FILES = ["library_hero.jpg", "header.jpg", "library_600x900.jpg"];
const PORTRAIT_FILES = ["library_600x900.jpg", "library_capsule.jpg"];

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(url));
    img.src = url;
  });
}

async function panelPixels(liveAppid: number, files = ART_FILES, width = PANEL_W): Promise<string | null> {
  for (const file of files) {
    try {
      const img = await loadImage(`/assets/${liveAppid}/${file}`);
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = PANEL_H;
      const ctx = canvas.getContext("2d");
      if (!ctx) return null;
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = "high";
      const crop = coverCrop(img.naturalWidth, img.naturalHeight, width, PANEL_H);
      ctx.drawImage(img, crop.sx, crop.sy, crop.sw, crop.sh, 0, 0, width, PANEL_H);
      const rgba = ctx.getImageData(0, 0, width, PANEL_H).data;
      let rgb = "";
      for (let i = 0; i < rgba.length; i += 4) rgb += String.fromCharCode(rgba[i], rgba[i + 1], rgba[i + 2]);
      return btoa(rgb);
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
  const missing = new Set<string>();
  let supported: boolean | null = null;
  const tick = async () => {
    if (!alive) return;
    if (supported === null) {
      try {
        supported = (await getAccessoriesState()).supported;
      } catch {
        return;
      }
    }
    if (!supported) return;
    const game = readRunningGame();
    if (!game || !Number.isFinite(game.liveAppid)) return;
    if (game.appid !== informed) {
      informed = game.appid;
      const portrait = await panelPixels(game.liveAppid, PORTRAIT_FILES, PORTRAIT_W);
      if (!alive) return;
      if (!(await sendGameInfo(game.appid, game.liveAppid, portrait))) informed = null;
    }
    if (game.appid === sent || missing.has(game.appid)) return;
    const rgb = await panelPixels(game.liveAppid);
    if (!alive) return;
    if (!rgb) {
      missing.add(game.appid);
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
