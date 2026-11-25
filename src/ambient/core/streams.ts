export type EmbedStream =
  | { provider: "twitch"; channel: string; video?: undefined }
  | { provider: "twitch"; video: string; channel?: undefined }
  | { provider: "kick"; channel: string }
  | { provider: "vimeo"; id: string }
  | { provider: "dailymotion"; id: string };

const CHANNEL = /^[A-Za-z0-9_]{2,40}$/;
const TWITCH_RESERVED = new Set(["directory", "videos", "p", "settings", "search", "downloads", "jobs", "turbo", "subscriptions", "inventory", "wallet", "friends", "messages"]);
const KICK_RESERVED = new Set(["categories", "browse", "following", "search", "video", "clips"]);

function parse(raw: string): URL | null {
  try {
    const url = new URL(raw);
    return url.protocol === "https:" || url.protocol === "http:" ? url : null;
  } catch {
    return null;
  }
}

/** Live and on-demand platforms Ambiente plays through their official embeds. */
export function parseEmbedStream(raw: string): EmbedStream | null {
  const url = parse(raw);
  if (!url) return null;
  const host = url.hostname.replace(/^(www|m)\./, "");
  const segments = url.pathname.split("/").filter(Boolean);
  if (host === "twitch.tv") {
    if (segments[0] === "videos" && /^\d{3,15}$/.test(segments[1] ?? "")) return { provider: "twitch", video: segments[1] };
    const channel = segments[0] ?? "";
    return CHANNEL.test(channel) && !TWITCH_RESERVED.has(channel.toLowerCase()) ? { provider: "twitch", channel: channel.toLowerCase() } : null;
  }
  if (host === "kick.com" || host === "player.kick.com") {
    const channel = segments[0] ?? "";
    return /^[A-Za-z0-9_-]{2,40}$/.test(channel) && !KICK_RESERVED.has(channel.toLowerCase()) ? { provider: "kick", channel: channel.toLowerCase() } : null;
  }
  if (host === "vimeo.com" || host === "player.vimeo.com") {
    const id = segments.find((s) => /^\d{5,12}$/.test(s));
    return id ? { provider: "vimeo", id } : null;
  }
  if (host === "dailymotion.com" || host === "dai.ly") {
    const id = host === "dai.ly" ? segments[0] : segments[0] === "video" || segments[0] === "embed" ? segments[segments[0] === "embed" ? 2 : 1] : undefined;
    return id && /^[A-Za-z0-9]{5,12}$/.test(id) ? { provider: "dailymotion", id } : null;
  }
  return null;
}

/** Channels on air have no end or seek bar; videos do. */
export function isLiveEmbed(stream: EmbedStream): boolean {
  return (stream.provider === "twitch" && !!stream.channel) || stream.provider === "kick";
}

export function embedLabel(stream: EmbedStream): string {
  return { twitch: "Twitch", kick: "Kick", vimeo: "Vimeo", dailymotion: "Dailymotion" }[stream.provider];
}
