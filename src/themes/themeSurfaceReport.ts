// Home carousel geometry at report time, so layout reports can be read without the reporter's
// screen. Only sizes and counts, never titles or app ids.
const HOME_ITEMS = '#Main [role="list"].ReactVirtualized__Grid__innerScrollContainer > [role="listitem"][data-id]';
const LIBRARY_ITEM = "GoToLibrary";

type SurfaceReport = Record<string, number | boolean | null>;

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
  const items = [...doc.querySelectorAll(HOME_ITEMS)];
  report.home_items = items.length;
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
    report.more_focused = !!more?.classList.contains("gpfocuswithin");
  }

  const canvases = [...doc.querySelectorAll("#Main canvas")].map(rectOf).filter((rect): rect is DOMRect => !!rect);
  report.main_canvases = canvases.length;
  if (canvases.length) report.main_canvas_h = Math.round(Math.max(...canvases.map((rect) => rect.height)));
  return report;
}
