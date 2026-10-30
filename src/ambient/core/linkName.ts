import { embedLabel, parseEmbedStream } from "./streams";
import { parseYouTube } from "./youtube";

/** A readable default name for a pasted link, so adding one is a single step. */
export function linkName(url: string): string {
  const video = parseYouTube(url);
  if (video) return video.listId && !video.videoId ? "YouTube · lista" : "YouTube";
  const embed = parseEmbedStream(url);
  if (embed) {
    const ref = "channel" in embed && embed.channel ? embed.channel : "";
    return ref ? `${embedLabel(embed)} · ${ref}` : embedLabel(embed);
  }
  try {
    const parsed = new URL(url);
    const file = parsed.pathname.split("/").filter(Boolean).pop();
    return file ? `${parsed.hostname} · ${decodeURIComponent(file)}` : parsed.hostname;
  } catch {
    return url;
  }
}
