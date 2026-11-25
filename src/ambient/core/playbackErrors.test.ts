import { describe, expect, it } from "vitest";

import { playbackProblem } from "./playbackErrors";

describe("playbackProblem", () => {
  it("explains YouTube, Twitch and stream failures", () => {
    expect(playbackProblem("https://youtu.be/dsuJZx24V_A", "media_error_150")).toBe("embedBlocked");
    expect(playbackProblem("https://youtu.be/dsuJZx24V_A", "media_error_100")).toBe("gone");
    expect(playbackProblem("https://www.twitch.tv/ibai", "media_error_100")).toBe("offline");
    expect(playbackProblem("https://radio.test/stream.mp3", "media_error_2")).toBe("network");
    expect(playbackProblem("https://radio.test/stream.mp3", "media_error_4")).toBe("format");
    expect(playbackProblem("https://radio.test/stream.mp3", null)).toBe("unknown");
  });
});
