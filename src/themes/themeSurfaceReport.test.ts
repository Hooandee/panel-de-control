// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";

import { themeSurfaceReport } from "./themeSurfaceReport";

function box(left: number, width: number, height: number) {
  return { left, right: left + width, top: 0, bottom: height, width, height, x: left, y: 0, toJSON() {} } as DOMRect;
}

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});

describe("themeSurfaceReport", () => {
  it("reports how the first cover sits against the second and where See more lands", () => {
    document.body.innerHTML = `<div id="Main"><div role="list" class="ReactVirtualized__Grid__innerScrollContainer">
      <div role="listitem" data-id="10"><div role="link" data-box="0,430,200"></div></div>
      <div role="listitem" data-id="20"><div role="link" data-box="420,150,225"></div></div>
      <div role="listitem" data-id="GoToLibrary" class="gpfocuswithin"><div role="link" data-box="300,190,92"></div></div>
    </div><canvas data-box="0,600,120"></canvas></div>`;
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
      const value = this.getAttribute("data-box");
      if (!value) return box(0, 0, 0);
      const [left, width, height] = value.split(",").map(Number);
      return box(left, width, height);
    });
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 1038 });
    Object.defineProperty(window, "innerHeight", { configurable: true, value: 584 });

    expect(themeSurfaceReport(window)).toEqual({
      vw: 1038, vh: 584, home_items: 3,
      first_w: 430, first_h: 200, first_wide: true, first_overlap: 10,
      more_center: -124,
      main_canvases: 1, main_canvas_h: 120,
    });
  });

  it("reports a Home host wider than the window (Steam's «Fondo ampliado», Loop 0.1.1 reports)", () => {
    document.body.innerHTML = `<div id="Main"><div data-box="0,22369620,584"><div class="ReactVirtualized__Grid" data-box="0,22369620,300"><div role="list" class="ReactVirtualized__Grid__innerScrollContainer" data-box="0,3391,300">
      <div role="listitem" data-id="10"><div role="link" data-box="0,430,200"></div></div>
    </div></div></div></div>`;
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
      const value = this.getAttribute("data-box");
      if (!value) return box(0, 0, 0);
      const [left, width, height] = value.split(",").map(Number);
      return box(left, width, height);
    });
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 854 });
    Object.defineProperty(window, "innerHeight", { configurable: true, value: 534 });

    expect(themeSurfaceReport(window).home_host_w).toBe(22369620);
  });

  it("ignores the carousel list itself, which is always wider than the screen", () => {
    document.body.innerHTML = `<div id="Main"><div data-box="0,854,584"><div class="ReactVirtualized__Grid" data-box="0,854,300"><div role="list" class="ReactVirtualized__Grid__innerScrollContainer" data-box="0,3391,300">
      <div role="listitem" data-id="10"><div role="link" data-box="0,430,200"></div></div>
    </div></div></div></div>`;
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
      const value = this.getAttribute("data-box");
      if (!value) return box(0, 0, 0);
      const [left, width, height] = value.split(",").map(Number);
      return box(left, width, height);
    });
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 854 });
    Object.defineProperty(window, "innerHeight", { configurable: true, value: 534 });

    expect(themeSurfaceReport(window)).not.toHaveProperty("home_host_w");
  });

  it("returns nothing without Big Picture", () => {
    expect(themeSurfaceReport(null)).toEqual({});
  });
});
