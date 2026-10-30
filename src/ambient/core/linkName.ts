import { embedLabel, parseEmbedStream } from "./streams";
import type { MediaKind } from "./types";
import { parseYouTube } from "./youtube";

/** A readable default name for a pasted link, so adding one is a single step. */
export function linkName(url: string): string {
  const video = parseYouTube(url);
  if (video) return "YouTube";
  const embed = parseEmbedStream(url);
  if (embed) return "channel" in embed && embed.channel ? embed.channel : embedLabel(embed);
  try {
    const parsed = new URL(url);
    const file = parsed.pathname.split("/").filter(Boolean).pop();
    return file ? decodeURIComponent(file).replace(/\.[a-z0-9]{2,5}$/i, "") : parsed.hostname;
  } catch {
    return url;
  }
}

/** What a direct file link holds, from its extension; null for pages and streams. */
export function linkKind(url: string): MediaKind | null {
  const path = url.split(/[?#]/)[0].toLowerCase();
  if (/\.(?:jpg|jpeg|png|webp|gif|bmp|avif)$/.test(path)) return "image";
  if (/\.(?:mp4|webm|mkv|mov|m4v)$/.test(path)) return "video";
  if (/\.(?:mp3|ogg|opus|flac|wav|m4a|aac)$/.test(path)) return "audio";
  return null;
}
