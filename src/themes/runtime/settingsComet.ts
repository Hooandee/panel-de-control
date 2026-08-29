const SETTINGS_TAB_SELECTOR = '.PageListColumn [id*="/settings/"][role="tab"]';
const COMET_Y = "--pdc-settings-comet-y";
const COMET_HEIGHT = "--pdc-settings-comet-height";

function restoreProperty(root: HTMLElement, name: string, previous: string): void {
  if (previous) root.style.setProperty(name, previous);
  else root.style.removeProperty(name);
}

export function startSettingsComet(doc: Document): () => void {
  const root = doc.documentElement;
  const previousState = root.getAttribute("data-pdc-settings-comet");
  const previousY = root.style.getPropertyValue(COMET_Y);
  const previousHeight = root.style.getPropertyValue(COMET_HEIGHT);
  let stopped = false;

  const clear = () => {
    root.removeAttribute("data-pdc-settings-comet");
    root.style.removeProperty(COMET_Y);
    root.style.removeProperty(COMET_HEIGHT);
  };
  const onFocus = (event: Event) => {
    const ElementType = doc.defaultView?.Element;
    if (typeof ElementType !== "function" || !(event.target instanceof ElementType)) {
      clear();
      return;
    }
    const tab = event.target.closest(SETTINGS_TAB_SELECTOR);
    if (!tab) {
      clear();
      return;
    }
    const rect = tab.getBoundingClientRect();
    if (rect.height <= 0) {
      clear();
      return;
    }
    root.dataset.pdcSettingsComet = "active";
    root.style.setProperty(COMET_Y, `${Math.round(rect.top + rect.height / 2)}px`);
    root.style.setProperty(COMET_HEIGHT, `${Math.round(rect.height)}px`);
  };

  doc.addEventListener("focusin", onFocus, true);
  doc.addEventListener("visibilitychange", clear);
  return () => {
    if (stopped) return;
    stopped = true;
    doc.removeEventListener("focusin", onFocus, true);
    doc.removeEventListener("visibilitychange", clear);
    if (previousState === null) root.removeAttribute("data-pdc-settings-comet");
    else root.setAttribute("data-pdc-settings-comet", previousState);
    restoreProperty(root, COMET_Y, previousY);
    restoreProperty(root, COMET_HEIGHT, previousHeight);
  };
}
