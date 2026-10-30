import { describe, expect, it } from "vitest";
import { libraryFavorites, photoSelection, preferredSource, visualSources } from "./libraryModel";

describe("shared library favorites", () => {
  const image = { id: "photo", name: "Photo", url: "https://example.test/image.jpg" };
  const video = { id: "video", name: "Video", url: "https://example.test/film.mp4" };
  const audio = { id: "song", name: "Song", url: "https://example.test/song.mp3" };
  it("offers the same saved video in both contexts while filtering image and audio", () => {
    expect(libraryFavorites([image, video], [audio], "background")).toEqual([image, video]);
    expect(libraryFavorites([image, video], [audio], "playback")).toEqual([video, audio]);
  });
  it("deduplicates existing scopes without replacing the background source identity", () => {
    expect(libraryFavorites([video], [{ ...video, id: "legacy-radio" }], "background")).toEqual([video]);
  });
  it("keeps embedded streams out of the background picker even if saved there previously", () => {
    const stream = { id: "youtube", name: "Stream", url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ" };
    expect(libraryFavorites([stream], [], "background")).toEqual([]);
    expect(libraryFavorites([stream], [], "playback")).toEqual([stream]);
  });
});

it("offers only sources containing visuals for background rotation", () => {
  const sources = [
    { id: "known.music", kind: "known" as const },
    { id: "folder.audio", kind: "folder" as const },
    { id: "folder.mixed", kind: "folder" as const },
    { id: "fav.radio", kind: "favorite" as const, url: "https://example.test/live" },
    { id: "fav.song", kind: "favorite" as const, url: "https://example.test/a.mp3" },
    { id: "suggested.nasa", kind: "suggested" as const },
  ];
  const audio = { id: "song", name: "Song", kind: "audio" as const, size: 1, mtime: 1 };
  const video = { ...audio, id: "video", kind: "video" as const };
  const scan = { library: { "known.music": [audio], "folder.audio": [audio], "folder.mixed": [audio, video] }, collections: {}, music: [audio], truncated: false };
  const radio = { id: "fav.radio", name: "Live", url: "https://example.test/live" };
  const song = { id: "fav.song", name: "Song", url: "https://example.test/a.mp3" };
  expect(visualSources(sources, scan, [song], [radio]).map((s) => s.id)).toEqual(["folder.mixed", "suggested.nasa"]);
});

it("defaults playback to the music source and background to its current suggested source", () => {
  const sources = [{ id: "folder.first", kind: "folder" as const }, { id: "known.music", kind: "known" as const }, { id: "suggested.nasa", kind: "suggested" as const }];
  expect(preferredSource(sources, null, "playback")).toBe("known.music");
  expect(preferredSource(sources, null, "background", "remote:photo", "suggested.nasa")).toBe("suggested.nasa");
});

it("rehydrates only photos and preserves the existing source when inventories overlap", () => {
  const photo = { ref: "local:photo", kind: "image" as const, name: "Photo", collection: "folder.chosen" };
  const video = { ref: "local:video", kind: "video" as const, name: "Video", collection: "folder.chosen" };
  const selected = photoSelection([photo.ref, video.ref, "local:missing", photo.ref], [photo, video, { ...photo, collection: "folder.parent" }]);
  expect([...selected.values()]).toEqual([photo]);
});
