import { accessoryEvent, getAccessoriesState } from "../api";
import { readRunningGame } from "../tdp/runningGame";
import { coverCrop, PANEL_H, PANEL_W } from "./pixelFrames";

const POLL_MS = 3000;
const ART_FILES = ["library_hero.jpg", "header.jpg", "library_600x900.jpg"];

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(url));
    img.src = url;
  });
}

async function panelPixels(liveAppid: number): Promise<string | null> {
  for (const file of ART_FILES) {
    try {
      const img = await loadImage(`/assets/${liveAppid}/${file}`);
      const canvas = document.createElement("canvas");
      canvas.width = PANEL_W;
      canvas.height = PANEL_H;
      const ctx = canvas.getContext("2d");
      if (!ctx) return null;
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = "high";
      const crop = coverCrop(img.naturalWidth, img.naturalHeight);
      ctx.drawImage(img, crop.sx, crop.sy, crop.sw, crop.sh, 0, 0, PANEL_W, PANEL_H);
      const rgba = ctx.getImageData(0, 0, PANEL_W, PANEL_H).data;
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
    if (!game || game.appid === sent || !Number.isFinite(game.liveAppid)) return;
    const rgb = await panelPixels(game.liveAppid);
    if (!alive || !rgb) return;
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
