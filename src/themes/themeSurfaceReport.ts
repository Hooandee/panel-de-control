// Report-time geometry and native web navigation, without titles, app ids, paths or URL contents.
const HOME_ITEMS = '#Main [role="list"].ReactVirtualized__Grid__innerScrollContainer > [role="listitem"][data-id]';
const LIBRARY_ITEM = "GoToLibrary";

type UrlKind = "blank" | "store" | "community" | "http" | "other";
interface NavigationReport {
  route: "home" | "steamweb" | "externalweb" | "store" | "other" | null;
  expected: UrlKind | null;
  requested: UrlKind | null;
  loaded: UrlKind | null;
  browser: "missing" | "unready" | "ready" | "unknown";
  loading: boolean | null;
  history: { index: number | null; entries: number | null; initial: number | null; final: number | null };
  error: number | null;
}
interface NavigationGlobals {
  SteamUIStore?: { WindowStore?: { GamepadUIMainWindowInstance?: {
    m_history?: { location?: { pathname?: unknown; state?: { url?: unknown; initialIndex?: unknown; finalIndex?: unknown } } };
    m_StoreBrowser?: {
      GetBrowser?: () => unknown;
      m_URLRequested?: unknown;
      m_URL?: unknown;
      m_bLoading?: unknown;
      History?: { index?: unknown; entries?: unknown };
      LoadErrorCode?: unknown;
    };
  } } };
}
type SurfaceReport = Record<string, number | boolean | null | NavigationReport>;

function reportInteger(value: unknown, minimum = 0): number | null {
  return typeof value === "number" && Number.isInteger(value) && value >= minimum && value <= 2147483647 ? value : null;
}

function urlKind(value: unknown): UrlKind | null {
  if (typeof value !== "string") return null;
  const normalized = value.trim().toLowerCase();
  if (["", "about:blank", "data:text/html,%3cbody%3e%3c%2fbody%3e", "data:text/html,<body></body>"].includes(normalized)) return "blank";
  try {
    const url = new URL(value);
    if (url.protocol !== "http:" && url.protocol !== "https:") return "other";
    if (url.hostname === "store.steampowered.com") return "store";
    if (url.hostname === "steamcommunity.com") return "community";
    return "http";
  } catch { return "other"; }
}

function navigationReport(): NavigationReport | null {
  try {
    const instance = (globalThis as NavigationGlobals).SteamUIStore?.WindowStore?.GamepadUIMainWindowInstance;
    if (!instance) return null;
    const location = instance.m_history?.location;
    const path = location?.pathname;
    const route = typeof path !== "string" ? null : path === "/library/home" ? "home"
      : /^\/steamweb(?:\/|$)/.test(path) ? "steamweb" : /^\/externalweb(?:\/|$)/.test(path) ? "externalweb"
        : path === "/store" ? "store" : "other";
    const browser = instance.m_StoreBrowser;
    const history = browser?.History;
    return {
      route,
      expected: urlKind(location?.state?.url),
      requested: urlKind(browser?.m_URLRequested),
      loaded: urlKind(browser?.m_URL),
      browser: !browser ? "missing" : typeof browser.GetBrowser !== "function" ? "unknown" : browser.GetBrowser() ? "ready" : "unready",
      loading: typeof browser?.m_bLoading === "boolean" ? browser.m_bLoading : null,
      history: {
        index: reportInteger(history?.index),
        entries: Array.isArray(history?.entries) ? history.entries.length : null,
        initial: reportInteger(location?.state?.initialIndex),
        final: reportInteger(location?.state?.finalIndex),
      },
      error: reportInteger(browser?.LoadErrorCode, -2147483648),
    };
  } catch { return null; }
}

function rectOf(element: Element | null | undefined): DOMRect | null {
  if (!element) return null;
  const rect = element.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0 ? rect : null;
}

function linkOf(item: Element | undefined): DOMRect | null {
  return rectOf(item?.querySelector('[role="link"]'));
}

export function themeSurfaceReport(view: Window | null | undefined): SurfaceReport {
  const doc = view?.document;
  if (!view || !doc) return {};
  const report: SurfaceReport = { vw: Math.round(view.innerWidth), vh: Math.round(view.innerHeight) };
  const navigation = navigationReport();
  if (navigation) report.navigation = navigation;
  const items = [...doc.querySelectorAll(HOME_ITEMS)];
  report.home_items = items.length;
  // A Home host wider than the window (Steam's «Fondo ampliado» lays Home out sideways) breaks themes that size
  // themselves from it: Loop 0.1.1 drew its shelf millions of pixels wide.
  const main = doc.querySelector("#Main");
  let widest = 0;
  // From the list's own viewport up: the list inside it is meant to be wider than the screen.
  for (let node = items[0]?.parentElement?.parentElement ?? null; node && node !== main; node = node.parentElement) {
    widest = Math.max(widest, node.getBoundingClientRect().width);
  }
  if (widest > view.innerWidth + 1) report.home_host_w = Math.round(widest);
  const covers = items.filter((item) => item.getAttribute("data-id") !== LIBRARY_ITEM);
  const first = linkOf(covers[0]);
  const second = linkOf(covers[1]);
  if (first) {
    report.first_w = Math.round(first.width);
    report.first_h = Math.round(first.height);
    report.first_wide = first.width > first.height;
  }
  if (first && second) report.first_overlap = Math.round(first.right - second.left);

  const stage = [...doc.querySelectorAll("[data-hdg-stage-card]")];
  if (stage.length) {
    report.stage_cards = stage.length;
    const face = (card: Element | undefined) => rectOf(card?.querySelector("[data-hdg-stage-face]") ?? card);
    const a = face(stage[0]);
    const b = face(stage[1]);
    if (a && b) report.stage_first_overlap = Math.round(a.right - b.left);
  }

  const more = items.find((item) => item.getAttribute("data-id") === LIBRARY_ITEM);
  const moreBox = rectOf(doc.querySelector('[data-hdg-stage-card="more"] [data-hdg-stage-face]'))
    ?? linkOf(more);
  if (moreBox) {
    report.more_center = Math.round(moreBox.left + moreBox.width / 2 - view.innerWidth / 2);
  }

  const canvases = [...doc.querySelectorAll("#Main canvas")].map(rectOf).filter((rect): rect is DOMRect => !!rect);
  report.main_canvases = canvases.length;
  if (canvases.length) report.main_canvas_h = Math.round(Math.max(...canvases.map((rect) => rect.height)));
  return report;
}
