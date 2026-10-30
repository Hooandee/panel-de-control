import { describe, expect, it } from "vitest";

import { linkName } from "./linkName";

describe("linkName", () => {
  it("names pasted links without asking", () => {
    expect(linkName("https://www.youtube.com/watch?v=dsuJZx24V_A")).toBe("YouTube");
    expect(linkName("https://www.youtube.com/playlist?list=PL123")).toBe("YouTube");
    expect(linkName("https://www.twitch.tv/ibai")).toBe("ibai");
    expect(linkName("https://tv.test/live/la1.m3u8")).toBe("la1");
    expect(linkName("https://music.test/Mi%20canci%C3%B3n.mp3")).toBe("Mi canción");
    expect(linkName("https://radio.test/")).toBe("radio.test");
  });
});
