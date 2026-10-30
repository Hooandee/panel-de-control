// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./steamClasses", () => ({ steamClass: (key: string) => ({ BasicHome: "hashedHome", RecentGamesBackground: "hashedHeroArt" })[key] ?? null }));

import { BackgroundLayer } from "./backgroundLayer";

const options = { transition: "fade" as const, nativeArt: "show" as const, motion: "play" as const, visible: true };

describe("BackgroundLayer", () => {
  let host: HTMLDivElement;

  beforeEach(() => {
    document.body.innerHTML = "";
    host = document.createElement("div");
    host.className = "hashedHome";
    host.appendChild(document.createElement("section"));
    document.body.appendChild(host);
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    vi.spyOn(HTMLImageElement.prototype, "decode").mockResolvedValue(undefined);
  });

  afterEach(() => vi.unstubAllGlobals());

  it("mounts as the host's first child and isolates the host", async () => {
    const layer = new BackgroundLayer(() => document);
    expect(layer.apply({ url: "http://127.0.0.1/a.jpg", kind: "image" }, options)).toBe(true);
    const root = host.firstElementChild as HTMLElement;
    expect(root.id).toBe("pdc-ambient-layer");
    expect(host.style.isolation).toBe("isolate");
    await vi.waitFor(() => expect(root.querySelector("[data-active] img")).not.toBeNull());
  });

  it("hides Steam's hero art by its wrapper class as well as by the legacy blurred file", () => {
    new BackgroundLayer(() => document).apply({ url: "http://127.0.0.1/a.jpg", kind: "image" }, { ...options, nativeArt: "hide" });
    const css = document.getElementById("pdc-ambient-layer-style")?.textContent ?? "";
    expect(css).toContain(':root[data-pdc-ambient-art=hide] .hashedHeroArt');
    expect(css).toContain(':root[data-pdc-ambient-art=hide] div:has(> img[src*="library_hero_blur"])');
    expect(css).toContain(':root[data-pdc-ambient-art=blend] .hashedHeroArt');
  });

  it("tells the page how Steam's game art shows over the layer", () => {
    const layer = new BackgroundLayer(() => document);
    layer.apply({ url: "http://127.0.0.1/a.jpg", kind: "image" }, { ...options, nativeArt: "hide" });
    expect(document.documentElement.getAttribute("data-pdc-ambient-art")).toBe("hide");
    layer.apply({ url: "http://127.0.0.1/a.jpg", kind: "image" }, { ...options, nativeArt: "blend" });
    expect(document.documentElement.getAttribute("data-pdc-ambient-art")).toBe("blend");
    layer.apply({ url: "http://127.0.0.1/a.jpg", kind: "image" }, options);
    expect(document.documentElement.hasAttribute("data-pdc-ambient-art")).toBe(false);
    layer.apply({ url: "http://127.0.0.1/a.jpg", kind: "image" }, { ...options, nativeArt: "hide" });
    layer.dispose();
    expect(document.documentElement.hasAttribute("data-pdc-ambient-art")).toBe(false);
  });

  it("asks Panel's media server for readable pictures and videos, and hands out the one on screen", async () => {
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    const layer = new BackgroundLayer(() => document);
    expect(layer.activeMedia()).toBeNull();
    layer.apply({ url: "http://127.0.0.1:4100/m/t/a.jpg", kind: "image" }, options);
    const img = await vi.waitFor(() => {
      const shown = layer.activeMedia();
      if (!shown) throw new Error("nothing shown yet");
      return shown;
    });
    expect(img.tagName).toBe("IMG");
    expect(img.crossOrigin).toBe("anonymous");
    layer.apply({ url: "http://127.0.0.1:4100/m/t/v.webm", kind: "video" }, options);
    const video = await vi.waitFor(() => {
      const v = host.querySelector("video");
      if (!v) throw new Error("no video yet");
      v.dispatchEvent(new Event("loadeddata"));
      return v;
    });
    expect(video.crossOrigin).toBe("anonymous");
    await vi.waitFor(() => expect(layer.activeMedia()).toBe(video));
    layer.apply({ url: "http://127.0.0.1:4100/m/t/v.webm", kind: "video" }, { ...options, visible: false });
    expect(layer.activeMedia()).toBeNull();
  });

  it("leaves Steam's own art without a CORS request", async () => {
    const layer = new BackgroundLayer(() => document);
    layer.apply({ url: "https://steamloopback.host/assets/10/library_hero.jpg", kind: "image" }, options);
    const img = await vi.waitFor(() => {
      const shown = layer.activeMedia();
      if (!shown) throw new Error("nothing shown yet");
      return shown;
    });
    expect(img.crossOrigin).toBeNull();
  });

  it("does nothing without the Steam host", () => {
    host.className = "other";
    expect(new BackgroundLayer(() => document).apply({ url: "x", kind: "image" }, options)).toBe(false);
  });

  it("hides when not visible and pauses videos when not playing", async () => {
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
    const layer = new BackgroundLayer(() => document);
    layer.apply({ url: "http://127.0.0.1/v.webm", kind: "video" }, options);
    const video = await vi.waitFor(() => {
      const v = host.querySelector("video");
      if (!v) throw new Error("no video yet");
      v.dispatchEvent(new Event("loadeddata"));
      return v;
    });
    await vi.waitFor(() => expect(video.closest("[data-active]")).not.toBeNull());
    pause.mockClear();
    layer.apply({ url: "http://127.0.0.1/v.webm", kind: "video" }, { ...options, motion: "freeze" });
    expect(pause).toHaveBeenCalled();
    layer.apply({ url: "http://127.0.0.1/v.webm", kind: "video" }, { ...options, visible: false });
    expect((host.firstElementChild as HTMLElement).style.display).toBe("none");
  });

  it("dispose leaves the DOM exactly as it was", () => {
    host.style.isolation = "auto";
    const layer = new BackgroundLayer(() => document);
    layer.apply({ url: "http://127.0.0.1/a.jpg", kind: "image" }, options);
    layer.dispose();
    expect(document.getElementById("pdc-ambient-layer")).toBeNull();
    expect(document.getElementById("pdc-ambient-layer-style")).toBeNull();
    expect(host.style.isolation).toBe("auto");
    expect(host.children.length).toBe(1);
  });

  it("null media removes the layer", () => {
    const layer = new BackgroundLayer(() => document);
    layer.apply({ url: "http://127.0.0.1/a.jpg", kind: "image" }, options);
    layer.apply(null, options);
    expect(layer.mounted).toBe(false);
  });

  it("repaint nudges the layer and clears the nudge", async () => {
    const layer = new BackgroundLayer(() => document);
    layer.apply({ url: "http://127.0.0.1/a.jpg", kind: "image" }, options);
    const root = document.getElementById("pdc-ambient-layer") as HTMLElement;
    layer.repaint();
    expect(root.style.outline).not.toBe("");
    await vi.waitFor(() => expect(root.style.outline).toBe(""));
  });
});

