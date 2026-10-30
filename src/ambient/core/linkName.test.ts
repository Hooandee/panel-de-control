import { describe, expect, it } from "vitest";

import { linkName } from "./linkName";

describe("linkName", () => {
  it("names pasted links without asking", () => {
    expect(linkName("https://www.youtube.com/watch?v=dsuJZx24V_A")).toBe("YouTube");
    expect(linkName("https://www.twitch.tv/ibai")).toBe("Twitch · ibai");
    expect(linkName("https://tv.test/live/la1.m3u8")).toBe("tv.test · la1.m3u8");
    expect(linkName("https://radio.test/")).toBe("radio.test");
  });
});
