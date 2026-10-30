import { describe, expect, it } from "vitest";

import { filterChannels, topGroups } from "./playlists";

const channels = [
  { id: "1", name: "La 1", url: "https://t/1.m3u8", logo: "", group: "Generalistas" },
  { id: "2", name: "La 2", url: "https://t/2.m3u8", logo: "", group: "Generalistas" },
  { id: "3", name: "24h", url: "https://t/3.m3u8", logo: "", group: "Noticias" },
  { id: "4", name: "Radio 3", url: "https://t/4.mp3", logo: "", group: "" },
];

describe("playlist helpers", () => {
  it("ranks groups by size", () => {
    expect(topGroups(channels)).toEqual(["Generalistas", "Noticias"]);
    expect(topGroups(channels, 1)).toEqual(["Generalistas"]);
  });

  it("filters by group and name", () => {
    expect(filterChannels(channels, "", "Noticias").map((c) => c.id)).toEqual(["3"]);
    expect(filterChannels(channels, "la ", null).map((c) => c.id)).toEqual(["1", "2"]);
    expect(filterChannels(channels, "radio", null).map((c) => c.id)).toEqual(["4"]);
  });
});
