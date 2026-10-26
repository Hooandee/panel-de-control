import { describe, expect, it, vi } from "vitest";
import { steamArtworkUrl } from "./artwork";
describe("Steam artwork paths", () => {
  it("accepts Steam registered custom and asset paths", () => {
    expect(steamArtworkUrl("/customimages/12p.png?v=4")).toBe("https://steamloopback.host/customimages/12p.png?v=4");
    expect(steamArtworkUrl("https://steamloopback.host/assets/12/hero.jpg")).toBeTruthy();
  });
  it("rejects remote downloads and other local resources", () => {
    for (const url of ["https://example.com/a.png", "//evil/assets/a", "/config/x", "/assets/../config/x", "javascript:alert(1)"]) expect(steamArtworkUrl(url)).toBeNull();
  });
});

import { artworkImages, previewArtworkImage, artworkSourceLabel, artworkGameTitle } from "./artworkImages";
import { DEFAULT_ARTWORK } from "./artwork";
it("previews DUO auto with hero and logo, and falls back to capsule when missing", () => {
  const images = [{ source: "capsule" as const, url: "capsule" }, { source: "hero" as const, url: "hero" }, { source: "logo" as const, url: "logo" }];
  expect(previewArtworkImage(DEFAULT_ARTWORK, images, [])).toBe("hero");
  expect(previewArtworkImage(DEFAULT_ARTWORK, images, ["hero"])).toBe("capsule");
  expect(previewArtworkImage(DEFAULT_ARTWORK, images, ["logo"])).toBe("capsule");
});

it("reads hero, logo and cached capsule paths exposed by Steam LCD while rejecting CDN", () => {
  vi.stubGlobal("window", {
    appStore: { GetAppOverviewByAppID: () => ({ appid: 1245620 }), GetCachedVerticalCapsuleURL: () => ["/assets/1245620/library_600x900.jpg?c=0"] },
    appDetailsStore: {
      GetHeroImagesForAppId: () => ({ rgHeroImages: ["/assets/1245620/library_hero.jpg?c=0", "https://cdn.example/hero.jpg"] }),
      GetLogoImagesForAppId: () => ({ rgLogoImages: ["/assets/1245620/logo.png?c=0"] }),
    },
  });
  try {
    expect(artworkImages(1245620)).toEqual([
      { source: "hero", url: "https://steamloopback.host/assets/1245620/library_hero.jpg?c=0" },
      { source: "logo", url: "https://steamloopback.host/assets/1245620/logo.png?c=0" },
      { source: "capsule", url: "https://steamloopback.host/assets/1245620/library_600x900.jpg?c=0" },
    ]);
  } finally { vi.unstubAllGlobals(); }
});

it("matches DUO auto with hidden logo and explicit source exhaustion", () => {
  const images = [{ source: "hero" as const, url: "hero" }, { source: "capsule" as const, url: "capsule" }, { source: "header" as const, url: "header" }];
  expect(previewArtworkImage({ ...DEFAULT_ARTWORK, showLogo: false }, images, [])).toBe("hero");
  expect(previewArtworkImage({ ...DEFAULT_ARTWORK, source: "hero" }, images, ["hero"])).toBe("capsule");
  expect(previewArtworkImage({ ...DEFAULT_ARTWORK, source: "hero" }, images, ["hero", "capsule"])).toBe("header");
  expect(previewArtworkImage({ ...DEFAULT_ARTWORK, source: "hero" }, images, ["hero", "capsule", "header"])).toBeUndefined();
});

it("uses human Spanish and English image labels", () => {
  expect(["hero", "capsule", "header"].map((source) => artworkSourceLabel(source as "hero" | "capsule" | "header", true))).toEqual(["Fondo", "Portada vertical", "Cabecera"]);
  expect(["hero", "capsule", "header"].map((source) => artworkSourceLabel(source as "hero" | "capsule" | "header", false))).toEqual(["Background", "Vertical cover", "Header"]);
});
it("gets the title from Steam even when the game is absent from installed games", () => {
  vi.stubGlobal("window", { appStore: { GetAppOverviewByAppID: () => ({ appid: 10, display_name: "Uninstalled game" }) } });
  try {
    expect(artworkGameTitle(10)).toBe("Uninstalled game");
    expect(artworkGameTitle(11, "Known game")).toBe("Known game");
  } finally { vi.unstubAllGlobals(); }
});
