import { safeArtworkUrl } from "./artwork";

const HOST_ID = "pdc-horizon-dossier";
const DETAILS_SENTINEL = '[role="tab"][aria-controls$="GameInfo_Content"]';
const HERO_SELECTOR = [
  'img[src*="/library_hero.jpg"]',
  'img[src*="/customimages/"][src*="_hero.jpg"]',
].join(",");

export interface HorizonDossier {
  show(main: Element, preferredArtwork?: string | null): boolean;
  clear(): void;
  dispose(): void;
}

function isHtmlElement(value: unknown, doc: Document): value is HTMLElement {
  const ElementType = doc.defaultView?.HTMLElement;
  return typeof ElementType === "function" && value instanceof ElementType;
}

function directTabs(rail: HTMLElement, doc: Document): HTMLElement[] {
  return Array.from(rail.children).filter((child): child is HTMLElement => (
    isHtmlElement(child, doc) && child.getAttribute("role") === "tab"
  ));
}

export function startHorizonDossier(doc: Document): HorizonDossier {
  const captured = new Map<Element, Map<string, string | null>>();
  const capturedStyles = new Map<HTMLElement, Map<string, { value: string; priority: string }>>();
  let activeMain: HTMLElement | null = null;
  let activeArtwork: string | null = null;
  let host: HTMLElement | null = null;
  let disposed = false;

  const mark = (element: Element, name: string, value = "true") => {
    let attributes = captured.get(element);
    if (!attributes) {
      attributes = new Map();
      captured.set(element, attributes);
    }
    if (!attributes.has(name)) attributes.set(name, element.getAttribute(name));
    element.setAttribute(name, value);
  };
  const style = (element: HTMLElement, name: string, value: string) => {
    let properties = capturedStyles.get(element);
    if (!properties) {
      properties = new Map();
      capturedStyles.set(element, properties);
    }
    if (!properties.has(name)) {
      properties.set(name, {
        value: element.style.getPropertyValue(name),
        priority: element.style.getPropertyPriority(name),
      });
    }
    element.style.setProperty(name, value, "important");
  };

  const restore = () => {
    for (const [element, attributes] of captured) {
      for (const [name, value] of attributes) {
        if (value === null) element.removeAttribute(name);
        else element.setAttribute(name, value);
      }
    }
    captured.clear();
    for (const [element, properties] of capturedStyles) {
      for (const [name, previous] of properties) {
        if (previous.value) element.style.setProperty(name, previous.value, previous.priority);
        else element.style.removeProperty(name);
      }
    }
    capturedStyles.clear();
  };

  const clear = () => {
    restore();
    host?.remove();
    host = null;
    activeMain = null;
    activeArtwork = null;
  };

  const createHost = (): HTMLElement | null => {
    if (!doc.body || doc.getElementById(HOST_ID)) return null;
    const next = doc.createElement("div");
    next.id = HOST_ID;
    next.setAttribute("aria-hidden", "true");
    next.style.pointerEvents = "none";
    for (const layer of ["void", "horizon", "frame"]) {
      const element = doc.createElement("div");
      element.dataset.pdcDossierLayer = layer;
      next.append(element);
    }
    for (let index = 0; index < 3; index += 1) {
      const node = doc.createElement("div");
      node.dataset.pdcDossierOrbitNode = String(index);
      next.append(node);
    }
    const panelFrame = doc.createElement("div");
    panelFrame.dataset.pdcDossierPanelFrame = "true";
    next.append(panelFrame);
    const cover = doc.createElement("div");
    cover.dataset.pdcDossierCover = "true";
    next.append(cover);
    doc.body.append(next);
    return next;
  };

  return {
    show(main, preferredArtwork = null) {
      if (disposed || !isHtmlElement(main, doc) || main.id !== "Main" || !main.isConnected) {
        clear();
        return false;
      }
      const sentinels = main.querySelectorAll(DETAILS_SENTINEL);
      if (sentinels.length !== 1 || !isHtmlElement(sentinels[0], doc)) {
        clear();
        return false;
      }
      const sentinel = sentinels[0];
      const rail = sentinel.parentElement;
      if (!rail || !main.contains(rail) || directTabs(rail, doc).length < 2) {
        clear();
        return false;
      }
      const heroImages = Array.from(main.querySelectorAll(HERO_SELECTOR))
        .filter((image): image is HTMLImageElement => {
          const ImageElement = doc.defaultView?.HTMLImageElement;
          return typeof ImageElement === "function" && image instanceof ImageElement;
        });
      const artwork = safeArtworkUrl(preferredArtwork ?? "")
        ?? heroImages.map((image) => safeArtworkUrl(image.currentSrc || image.src)).find(Boolean)
        ?? (activeMain === main ? activeArtwork : null);
      if (!artwork) {
        clear();
        return false;
      }
      if (activeMain !== main) clear();
      if (!host) {
        host = createHost();
        if (!host) return false;
      }
      activeMain = main;
      activeArtwork = artwork;
      host.style.setProperty("--pdc-dossier-artwork", `url(${JSON.stringify(artwork)})`);
      mark(main, "data-pdc-horizon-dossier");
      style(main, "background", "linear-gradient(180deg,transparent 0 38%,rgba(1,3,8,.9) 58%,#010207 100%)");
      mark(rail, "data-pdc-dossier-tabs");
      for (const tab of directTabs(rail, doc)) mark(tab, "data-pdc-dossier-tab");
      for (const image of heroImages) mark(image, "data-pdc-dossier-hero");

      const buttons = Array.from(main.querySelectorAll('[role="button"]'))
        .filter((button): button is HTMLElement => isHtmlElement(button, doc));
      for (const button of buttons) {
        style(button, "-webkit-backdrop-filter", "none");
        style(button, "backdrop-filter", "none");
      }

      const panels = Array.from(main.querySelectorAll('[role="tabpanel"]'))
        .filter((panel): panel is HTMLElement => isHtmlElement(panel, doc));
      for (const panel of panels) {
        mark(panel, "data-pdc-dossier-content");
        for (const card of panel.querySelectorAll('[role="button"]')) {
          mark(card, "data-pdc-dossier-card");
          if (isHtmlElement(card, doc)) {
            style(card, "-webkit-backdrop-filter", "none");
            style(card, "backdrop-filter", "none");
            style(card, "background", "linear-gradient(112deg,rgba(9,22,34,.96),rgba(10,9,19,.98))");
          }
        }
      }

      const railRect = rail.getBoundingClientRect();
      if (railRect.top > 0) {
        const primary = buttons.find((button) => {
            if (button.closest('[role="tabpanel"], #header')) return false;
            const rect = button.getBoundingClientRect();
            return rect.width >= 120 && rect.height >= 32 && rect.top < railRect.top;
          });
        if (primary) {
          mark(primary, "data-pdc-dossier-primary-action");
          style(primary, "-webkit-backdrop-filter", "none");
          style(primary, "backdrop-filter", "none");
          style(primary, "background", "linear-gradient(108deg,#d9feff 0 4px,#0b6175 4px 68%,#1c1839 100%)");
        }
      }
      return true;
    },
    clear,
    dispose() {
      if (disposed) return;
      disposed = true;
      clear();
    },
  };
}
