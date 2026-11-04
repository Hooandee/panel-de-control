// @vitest-environment happy-dom
import { describe, expect, it, vi } from "vitest";

vi.mock("@decky/ui", () => ({ findSP: () => null }));
vi.mock("@decky/api", () => ({ routerHook: {}, callable: () => vi.fn() }));

import { hostOf, tileOf } from "./overlays";

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
});
