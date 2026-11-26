// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({ findSP: () => null }));
vi.mock("@decky/api", () => ({ routerHook: {}, callable: () => vi.fn(() => Promise.resolve()) }));

import { renderHook } from "@testing-library/react";
import { hostOf, isCollection, isHidden, publishOverview, tileOf, useInstalls } from "./overlays";
import type { UpscalersOverview } from "./types";

function box(el: Element, width: number, height: number): void {
  el.getBoundingClientRect = () => ({ x: 0, y: 0, left: 0, top: 0, width, height, right: width, bottom: height, toJSON: () => ({}) });
}

describe("cover badge placement", () => {
  it("hangs the pill on the image's own wrapper so the focused tile's lifted layer cannot cover it", () => {
    // Steam's recent-games capsule: an outer static wrapper, then the focus-lifted layer (z-index 12), then the art box.
    const row = document.createElement("div");
    const outer = document.createElement("div");
    const lifted = document.createElement("div");
    const art = document.createElement("div");
    const img = document.createElement("img");
    art.appendChild(img);
    lifted.appendChild(art);
    outer.appendChild(lifted);
    row.appendChild(outer);
    document.body.appendChild(row);
    box(row, 430, 253);
    box(outer, 430, 201);
    box(lifted, 440, 206);
    box(art, 440, 206);
    box(img, 440, 206);

    const tile = tileOf(img)!;
    expect(tile).toBe(outer);
    expect(hostOf(img, tile)).toBe(art);
  });

  it("falls back to the tile when the image's wrapper is cropped by a round tile", () => {
    // Eclipse orbs: a portrait wrapper inside a smaller round clip.
    const tileBox = document.createElement("div");
    const wrapper = document.createElement("div");
    const img = document.createElement("img");
    wrapper.appendChild(img);
    tileBox.appendChild(wrapper);
    document.body.appendChild(tileBox);
    box(tileBox, 107, 107);
    box(wrapper, 107, 160);
    box(img, 107, 160);

    expect(hostOf(img, tileBox)).toBe(tileBox);
  });

  it("leaves collection collages alone", () => {
    const item = document.createElement("div");
    item.className = "Focusable";
    for (const appid of ["548430", "2246340"]) {
      const cell = document.createElement("div");
      const img = document.createElement("img");
      img.src = `https://steamloopback.host/assets/${appid}/library_600x900.jpg`;
      cell.appendChild(img);
      item.appendChild(cell);
    }
    document.body.appendChild(item);
    box(item, 185, 185);
    box(item.querySelector("div")!, 103, 96);
    expect(isCollection(item.querySelector("div")!)).toBe(true);

    // A theme's whole home screen as one selectable item still badges each card.
    box(item, 854, 534);
    expect(isCollection(item.querySelector("div")!)).toBe(false);

    const single = document.createElement("div");
    single.className = "Focusable";
    const img = document.createElement("img");
    img.src = "https://steamloopback.host/assets/548430/library_600x900.jpg";
    single.appendChild(img);
    document.body.appendChild(single);
    expect(isCollection(single)).toBe(false);
  });

  it("stops at the card when Steam wraps it in a collapsed grid cell", () => {
    const cell = document.createElement("div");
    const card = document.createElement("div");
    const img = document.createElement("img");
    card.appendChild(img);
    cell.appendChild(card);
    document.body.appendChild(cell);
    box(cell, 0, 0);
    box(card, 134, 201);
    box(img, 134, 201);
    expect(tileOf(img)).toBe(card);
  });
});

describe("screen-wide carousels", () => {
  it("are not taken for a collection collage", () => {
    const carousel = document.createElement("div");
    carousel.className = "Focusable";
    const face = document.createElement("div");
    const faceImg = document.createElement("img");
    faceImg.src = "https://steamloopback.host/assets/1462040/library_header.jpg";
    const neighbour = document.createElement("img");
    neighbour.src = "https://steamloopback.host/assets/292030/library_600x900.jpg";
    face.appendChild(faceImg);
    carousel.append(face, neighbour);
    document.body.appendChild(carousel);
    box(carousel, window.innerWidth, 508);
    box(face, window.innerWidth / 1.8, 231);
    expect(isCollection(face)).toBe(false);
    carousel.remove();
  });
});

describe("hidden art", () => {
  it("never carries the pill when a theme hides Steam's image under its own copy", () => {
    const card = document.createElement("div");
    const hiddenLayer = document.createElement("div");
    hiddenLayer.style.opacity = "0";
    const original = document.createElement("img");
    const copy = document.createElement("img");
    hiddenLayer.appendChild(original);
    card.append(hiddenLayer, copy);
    document.body.appendChild(card);
    expect(isHidden(original, window)).toBe(true);
    expect(isHidden(copy, window)).toBe(false);
    card.remove();
  });
});

describe("installs published before the overlays subscribe", () => {
  it("still reach a component whose subscription effect runs after the publish", async () => {
    const { render, cleanup } = await import("@testing-library/react");
    const { createElement, useLayoutEffect } = await import("react");
    const { publishOverview, useInstalls } = await import("./overlays");
    const seen: string[][] = [];
    const Reader = () => {
      seen.push(Object.keys(useInstalls()));
      return null;
    };
    const EarlyPublish = () => {
      useLayoutEffect(() => {
        publishOverview({
          installs: { "292030": { build: "fsr-3.1", status: "active" } },
          builds: [{ id: "fsr-3.1", family: "fsr", version: "3.1.5" }],
        } as never);
      }, []);
      return null;
    };
    render(createElement("div", null, createElement(Reader), createElement(EarlyPublish)));
    expect(seen[seen.length - 1]).toEqual(["292030"]);
    cleanup();
  });
});

describe("covers without an upscaler install", () => {
  it("name Mako or Lossless Scaling instead of staying blank", async () => {
    const { publishOverview } = await import("./overlays");
    expect(() => publishOverview({ builds: [], installs: {}, engines: { "292030": { mako: { spatial: true, fg: false, multiplier: null } } } } as never)).not.toThrow();
  });
});

describe("cover badges switch", () => {
  it("is on until turned off, and the choice is kept", async () => {
    const { readCoverBadges, writeCoverBadges } = await import("./overlays");
    expect(readCoverBadges()).toBe(true);
    writeCoverBadges(false);
    expect(readCoverBadges()).toBe(false);
    writeCoverBadges(true);
    expect(readCoverBadges()).toBe(true);
  });
});

describe("cover badge for themes that paint covers", () => {
  const overview = {
    builds: [{ id: "fsr-4.1.2-beta", engine: "optiscaler", family: "fsr", version: "4.1.2", models: ["lite"] }],
    installs: { "1245620": { build: "fsr-4.1.2-beta", status: "installed", options: { model: "lite" } } },
  } as unknown as UpscalersOverview;

  it("gives the same text as the DOM pill, follows installs and removals and honours the hide option", async () => {
    const { coverBadgeFor, subscribeCoverBadges, writeCoverBadges } = await import("./overlays");
    const changed = vi.fn();
    const stop = subscribeCoverBadges(changed);
    publishOverview(overview);
    expect(coverBadgeFor("1245620")).toEqual({ label: "FSR 4.1.2 Lite", short: "FSR 4 Lite", state: "installed" });
    expect(coverBadgeFor("7")).toBeNull();
    expect(changed).toHaveBeenCalledTimes(1);
    publishOverview(overview);
    expect(changed).toHaveBeenCalledTimes(1);
    writeCoverBadges(false);
    expect(coverBadgeFor("1245620")).toBeNull();
    expect(changed).toHaveBeenCalledTimes(2);
    writeCoverBadges(true);
    expect(changed).toHaveBeenCalledTimes(3);
    publishOverview({ ...overview, installs: {} });
    expect(coverBadgeFor("1245620")).toBeNull();
    expect(changed).toHaveBeenCalledTimes(4);
    stop();
    publishOverview(overview);
    expect(changed).toHaveBeenCalledTimes(4);
  });
});

describe("cover badge listeners", () => {
  it("keep being called when another one throws", async () => {
    const { subscribeCoverBadges, writeCoverBadges } = await import("./overlays");
    const good = vi.fn();
    writeCoverBadges(true);
    const stopBad = subscribeCoverBadges(() => { throw new Error("theme"); });
    const stopGood = subscribeCoverBadges(good);
    publishOverview({ builds: [{ id: "fsr-4.1.2-beta", engine: "optiscaler", family: "fsr", version: "4.1.2", models: ["lite"] }],
      installs: { "99": { build: "fsr-4.1.2-beta", status: "installed", options: { model: "lite" } } } } as unknown as UpscalersOverview);
    expect(good).toHaveBeenCalledTimes(1);
    stopBad(); stopGood();
    publishOverview({ builds: [], installs: {} } as unknown as UpscalersOverview);
  });
});

describe("cover pill when FSR 4 fell back", () => {
  const overview = (fallback: unknown) => ({
    builds: [{ id: "fsr-4.1.2-beta", family: "fsr", version: "4.1.2", models: ["lite", "full"], engine: "optiscaler" }],
    installs: { "4732690": { build: "fsr-4.1.2-beta", proxy: "d3d12.dll", status: "active", options: { model: "lite" }, fallback } },
  }) as unknown as UpscalersOverview;

  it("names the scaler that runs instead of the installed one", () => {
    publishOverview(overview({ requested: "FSR 4", observed: "FSR 2.2", reason: "vulkan_textures" }));
    const badge = renderHook(() => useInstalls()).result.current["4732690"];
    expect(badge.state).toBe("fallback");
    expect(badge.label).toContain("FSR 2.2");
    expect(badge.label).not.toContain("Lite");
  });

  it("keeps the installed label when nothing fell back", () => {
    publishOverview(overview(null));
    const badge = renderHook(() => useInstalls()).result.current["4732690"];
    expect(badge.state).toBe("active");
    expect(badge.label).toBe("FSR 4.1.2 Lite");
  });
});
