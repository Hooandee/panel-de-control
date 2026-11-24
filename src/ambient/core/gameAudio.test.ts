import { describe, expect, it } from "vitest";

import { pickGameAudio } from "./gameAudio";

const both = { theme: true, trailer: true };
const onlyTheme = { theme: true, trailer: false };
const onlyTrailer = { theme: false, trailer: true };
const none = { theme: false, trailer: false };

describe("pickGameAudio", () => {
  it("auto keeps the soundtrack first and the trailer as the fallback", () => {
    expect(pickGameAudio("auto", both)).toBe("theme");
    expect(pickGameAudio("auto", onlyTrailer)).toBe("trailer");
    expect(pickGameAudio("auto", onlyTheme)).toBe("theme");
    expect(pickGameAudio("auto", none)).toBeNull();
  });

  it("trailerFirst prefers the trailer and falls back to the soundtrack", () => {
    expect(pickGameAudio("trailerFirst", both)).toBe("trailer");
    expect(pickGameAudio("trailerFirst", onlyTheme)).toBe("theme");
    expect(pickGameAudio("trailerFirst", none)).toBeNull();
  });

  it("the exclusive choices stay silent when their source is missing", () => {
    expect(pickGameAudio("musicOnly", both)).toBe("theme");
    expect(pickGameAudio("musicOnly", onlyTrailer)).toBeNull();
    expect(pickGameAudio("trailerOnly", both)).toBe("trailer");
    expect(pickGameAudio("trailerOnly", onlyTheme)).toBeNull();
  });
});
