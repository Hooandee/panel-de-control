import { parseEmbedStream } from "./streams";
import { parseYouTube } from "./youtube";

export type PlaybackProblem = "offline" | "embedBlocked" | "gone" | "network" | "format" | "unknown";

/**
 * Why a track failed, from the player's `media_error_<code>`: YouTube's iframe codes, Twitch's
 * offline signal, the page's load failure, or the media element's own error codes.
 */
export function playbackProblem(url: string, error: string | null): PlaybackProblem {
  const code = Number(/media_error_(\d+)/.exec(error ?? "")?.[1] ?? Number.NaN);
  if (Number.isNaN(code)) return "unknown";
  if (parseYouTube(url)) {
    if (code === 101 || code === 150) return "embedBlocked";
    if (code === 100) return "gone";
    return code === 5 ? "network" : "unknown";
  }
  if (parseEmbedStream(url)?.provider === "twitch" && code === 100) return "offline";
  if (code === 2 || code === 5) return "network";
  if (code === 3 || code === 4) return "format";
  return "unknown";
}
