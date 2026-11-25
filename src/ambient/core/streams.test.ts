import { describe, expect, it } from "vitest";

import { isLiveEmbed, parseEmbedStream } from "./streams";

describe("parseEmbedStream", () => {
  it("reads Twitch channels and videos", () => {
    expect(parseEmbedStream("https://www.twitch.tv/Ibai")).toEqual({ provider: "twitch", channel: "ibai" });
    expect(parseEmbedStream("https://m.twitch.tv/videos/2255887766")).toEqual({ provider: "twitch", video: "2255887766" });
    expect(parseEmbedStream("https://www.twitch.tv/directory")).toBeNull();
  });

  it("reads Kick, Vimeo and Dailymotion", () => {
    expect(parseEmbedStream("https://kick.com/westcol")).toEqual({ provider: "kick", channel: "westcol" });
    expect(parseEmbedStream("https://vimeo.com/76979871")).toEqual({ provider: "vimeo", id: "76979871" });
    expect(parseEmbedStream("https://player.vimeo.com/video/76979871")).toEqual({ provider: "vimeo", id: "76979871" });
    expect(parseEmbedStream("https://www.dailymotion.com/video/x8abcd1")).toEqual({ provider: "dailymotion", id: "x8abcd1" });
    expect(parseEmbedStream("https://dai.ly/x8abcd1")).toEqual({ provider: "dailymotion", id: "x8abcd1" });
  });

  it("ignores everything else", () => {
    expect(parseEmbedStream("https://youtu.be/dsuJZx24V_A")).toBeNull();
    expect(parseEmbedStream("https://evil.test/twitch.tv/ibai")).toBeNull();
    expect(parseEmbedStream("javascript:alert(1)")).toBeNull();
  });

  it("knows which ones are live", () => {
    expect(isLiveEmbed({ provider: "twitch", channel: "ibai" })).toBe(true);
    expect(isLiveEmbed({ provider: "twitch", video: "1" })).toBe(false);
    expect(isLiveEmbed({ provider: "vimeo", id: "1" })).toBe(false);
  });
});
