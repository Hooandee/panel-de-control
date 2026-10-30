import { parseEmbedStream } from "./streams";

export interface YouTubeRef {
  videoId: string | null;
  listId: string | null;
}

const VIDEO_ID = /^[A-Za-z0-9_-]{11}$/;
const LIST_ID = /^[A-Za-z0-9_-]{2,64}$/;
const HOSTS = new Set(["youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be", "www.youtube-nocookie.com"]);

export function parseYouTube(raw: string): YouTubeRef | null {
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    return null;
  }
  if (!HOSTS.has(url.hostname)) return null;
  const segments = url.pathname.split("/").filter(Boolean);
  const candidate = url.hostname === "youtu.be"
    ? segments[0]
    : segments[0] === "watch" ? url.searchParams.get("v")
    : ["embed", "shorts", "live"].includes(segments[0]) ? segments[1]
    : null;
  const videoId = candidate && VIDEO_ID.test(candidate) ? candidate : null;
  const list = url.searchParams.get("list");
  const listId = list && LIST_ID.test(list) ? list : null;
  return videoId || listId ? { videoId, listId } : null;
}

export function youTubeEmbedUrl(ref: YouTubeRef, origin: string): string {
  const params = new URLSearchParams({ autoplay: "1", enablejsapi: "1", playsinline: "1", controls: "0", origin });
  if (ref.listId) params.set("list", ref.listId);
  const path = ref.videoId ?? "videoseries";
  return `https://www.youtube.com/embed/${path}?${params.toString()}`;
}

export function youTubeThumbnail(videoId: string): string {
  return `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`;
}

const DIRECT_VIDEO = /\.(mp4|webm|mkv|mov|m4v)(\?|#|$)/i;

const HLS = /\.m3u8(\?|#|$)/i;

/** HLS (IPTV, some radios) needs hls.js, which only the video window page carries. */
export function isHls(url: string): boolean {
  return /^https?:\/\//.test(url) && HLS.test(url);
}

/** YouTube links, direct video files and HLS streams can open in the video window. */
export function canShowVideo(url: string): boolean {
  return parseYouTube(url) !== null || parseEmbedStream(url) !== null || isHls(url) || (/^https?:\/\//.test(url) && DIRECT_VIDEO.test(url));
}
