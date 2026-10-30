import { describe, expect, it } from "vitest";

import { canShowVideo, isHls, parseYouTube, youTubeEmbedUrl, youTubeThumbnail } from "./youtube";

describe("parseYouTube", () => {
  it("reads a watch link with a mix list", () => {
    expect(parseYouTube("https://www.youtube.com/watch?v=dsuJZx24V_A&list=RDdsuJZx24V_A&start_radio=1"))
      .toEqual({ videoId: "dsuJZx24V_A", listId: "RDdsuJZx24V_A" });
  });

  it("reads short, shorts, music and playlist links", () => {
    expect(parseYouTube("https://youtu.be/dsuJZx24V_A?t=3")).toEqual({ videoId: "dsuJZx24V_A", listId: null });
    expect(parseYouTube("https://youtube.com/shorts/dsuJZx24V_A")).toEqual({ videoId: "dsuJZx24V_A", listId: null });
    expect(parseYouTube("https://music.youtube.com/watch?v=dsuJZx24V_A")).toEqual({ videoId: "dsuJZx24V_A", listId: null });
    expect(parseYouTube("https://www.youtube.com/playlist?list=PL1234567890")).toEqual({ videoId: null, listId: "PL1234567890" });
  });

  it("rejects other hosts and malformed ids", () => {
    expect(parseYouTube("https://stream.example/radio.mp3")).toBeNull();
    expect(parseYouTube("https://evil.com/watch?v=dsuJZx24V_A")).toBeNull();
    expect(parseYouTube("https://www.youtube.com/watch?v=short")).toBeNull();
    expect(parseYouTube("not a url")).toBeNull();
  });
});

describe("youTubeEmbedUrl", () => {
  it("builds an autoplaying API embed for the loopback origin", () => {
    const url = new URL(youTubeEmbedUrl({ videoId: "dsuJZx24V_A", listId: "RDdsuJZx24V_A" }, "https://steamloopback.host"));
    expect(url.pathname).toBe("/embed/dsuJZx24V_A");
    expect(url.searchParams.get("enablejsapi")).toBe("1");
    expect(url.searchParams.get("autoplay")).toBe("1");
    expect(url.searchParams.get("list")).toBe("RDdsuJZx24V_A");
    expect(url.searchParams.get("origin")).toBe("https://steamloopback.host");
  });

  it("uses the playlist embed when there is no video", () => {
    expect(new URL(youTubeEmbedUrl({ videoId: null, listId: "PL1234567890" }, "o")).pathname).toBe("/embed/videoseries");
  });

  it("points thumbnails at the image CDN", () => {
    expect(youTubeThumbnail("dsuJZx24V_A")).toBe("https://i.ytimg.com/vi/dsuJZx24V_A/hqdefault.jpg");
  });
});

describe("canShowVideo", () => {
  it("accepts YouTube and direct video files only", () => {
    expect(canShowVideo("https://youtu.be/dsuJZx24V_A")).toBe(true);
    expect(canShowVideo("https://cdn.test/clip.mp4?x=1")).toBe(true);
    expect(canShowVideo("https://stream.test/radio.mp3")).toBe(false);
    expect(canShowVideo("file:///clip.mp4")).toBe(false);
  });
});

describe("isHls", () => {
  it("spots HLS playlists over http(s)", () => {
    expect(isHls("https://tv.test/la1/main.m3u8")).toBe(true);
    expect(isHls("https://tv.test/la1/main.m3u8?token=1")).toBe(true);
    expect(isHls("https://tv.test/radio.mp3")).toBe(false);
    expect(canShowVideo("https://tv.test/la1/main.m3u8")).toBe(true);
  });
});
