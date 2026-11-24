// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";

import { themeSurfaceReport } from "./themeSurfaceReport";
import steamWebStates from "./fixtures/steam-web-states.json";

function box(left: number, width: number, height: number) {
  return { left, right: left + width, top: 0, bottom: height, width, height, x: left, y: 0, toJSON() {} } as DOMRect;
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
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

function navigationSource(state: typeof steamWebStates[number]["state"]) {
  return { WindowStore: { GamepadUIMainWindowInstance: {
    m_history: { location: { pathname: state.route, state: state.routeState } },
    ...(state.browserExists ? { m_StoreBrowser: {
      m_URLRequested: state.requested, m_URL: state.url, m_bLoading: state.loading, History: state.history,
    } } : {}),
  } } };
}

it.each(steamWebStates)("captures the native store loading state without copying its URLs: %#", ({ state, want }) => {
  vi.stubGlobal("SteamUIStore", navigationSource(state));
  expect(themeSurfaceReport(window).navigation).toEqual(want);
});

it("keeps private paths, tokens, titles and errors out of the navigation snapshot", () => {
  const source = navigationSource(steamWebStates[2]!.state);
  const instance = source.WindowStore.GamepadUIMainWindowInstance;
  instance.m_history.location.pathname = "/chat/private-account";
  instance.m_history.location.state = { url: "https://steamcommunity.com/id/private-account/?token=private-secret", initialIndex: -1, finalIndex: 1.5 };
  const browser = Object.assign(instance.m_StoreBrowser!, {
    m_URLRequested: "https://store.steampowered.com.evil.test/private-secret",
    m_URL: "data:text/html,private-secret",
    m_loadErrorDesc: "private-secret", LoadErrorCode: -105,
    GetBrowser: () => ({}),
    History: { index: 1, entries: [{ url: "https://example.test/private-secret", title: "private-secret" }] },
  });
  instance.m_StoreBrowser = browser;
  vi.stubGlobal("SteamUIStore", source);
  const report = themeSurfaceReport(window);
  expect(report.navigation).toEqual({ route: "other", expected: "community", requested: "http", loaded: "other", browser: "ready", loading: false, history: { index: 1, entries: 1, initial: null, final: null }, error: -105 });
  expect(JSON.stringify(report)).not.toContain("private");
});

it("keeps geometry available when Steam's navigation source throws", () => {
  vi.stubGlobal("SteamUIStore", { get WindowStore(): never { throw new Error("unavailable"); } });
  expect(themeSurfaceReport(window)).toMatchObject({ home_items: 0, main_canvases: 0 });
  expect(themeSurfaceReport(window)).not.toHaveProperty("navigation");
});

it.each([
  { path: "/store", url: "https://store.steampowered.com/", route: "store", expected: "store" },
  { path: "/externalweb", url: "about:blank", route: "externalweb", expected: "blank" },
])("identifies native web routes without retaining the destination: $path", ({ path, url, route, expected }) => {
  const source = navigationSource(steamWebStates[0]!.state);
  source.WindowStore.GamepadUIMainWindowInstance.m_history.location = { pathname: path, state: { url } };
  vi.stubGlobal("SteamUIStore", source);
  expect(themeSurfaceReport(window).navigation).toMatchObject({ route, expected });
});
