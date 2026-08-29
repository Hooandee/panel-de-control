const STAGE_ID = "pdc-orbital-abyss";
const ORBIT_RADIUS_X = 38;
const ORBIT_RADIUS_Y = 20;
const ORBIT_CENTER_Y = 40;
const VISIBLE_RADIUS = 4;
const CAPTION_SYNC_FRAMES = 4;
const NATIVE_PLAY_PATH = "M7.5 32.135a1 1 0 0 1-1.5-.866V4.73a1 1 0 0 1 1.5-.866l22.999 13.269a1 1 0 0 1 0 1.732l-23 13.269Z";
const NATIVE_DOWNLOAD_PATHS = [
  "M29 23V27H7V23H2V32H34V23H29Z",
  "M20 14.1716L24.5858 9.58578L27.4142 12.4142L18 21.8284L8.58582 12.4142L11.4142 9.58578L16 14.1715V2H20V14.1716Z",
] as const;

interface ElementSnapshot {
  attributes: Map<string, string | null>;
  styles: Map<string, string>;
}

interface SteamCopy {
  title: string;
  titleElements: HTMLElement[];
  meta: string;
  metaElements: HTMLElement[];
}

export type OrbitalCaptionAction = "play" | "download" | null;

export interface OrbitalAbyssOptions {
  resolveAction?: (appid: number) => OrbitalCaptionAction;
}

class MutationLedger {
  private readonly snapshots = new Map<HTMLElement, ElementSnapshot>();

  private snapshot(element: HTMLElement): ElementSnapshot {
    const existing = this.snapshots.get(element);
    if (existing) return existing;
    const created = { attributes: new Map<string, string | null>(), styles: new Map<string, string>() };
    this.snapshots.set(element, created);
    return created;
  }

  attribute(element: HTMLElement, name: string, value: string): void {
    const snapshot = this.snapshot(element);
    if (!snapshot.attributes.has(name)) snapshot.attributes.set(name, element.getAttribute(name));
    element.setAttribute(name, value);
  }

  style(element: HTMLElement, name: string, value: string): void {
    const snapshot = this.snapshot(element);
    if (!snapshot.styles.has(name)) snapshot.styles.set(name, element.style.getPropertyValue(name));
    element.style.setProperty(name, value);
  }

  restore(): void {
    for (const [element, snapshot] of this.snapshots) {
      for (const [name, value] of snapshot.attributes) {
        if (value === null) element.removeAttribute(name);
        else element.setAttribute(name, value);
      }
      for (const [name, value] of snapshot.styles) {
        if (value) element.style.setProperty(name, value);
        else element.style.removeProperty(name);
      }
    }
    this.snapshots.clear();
  }
}

class AttributeLedger {
  private readonly snapshots = new Map<Element, Map<string, string | null>>();

  attribute(element: Element, name: string, value: string): void {
    let snapshot = this.snapshots.get(element);
    if (!snapshot) {
      snapshot = new Map();
      this.snapshots.set(element, snapshot);
    }
    if (!snapshot.has(name)) snapshot.set(name, element.getAttribute(name));
    element.setAttribute(name, value);
  }

  restore(): void {
    for (const [element, attributes] of this.snapshots) {
      for (const [name, value] of attributes) {
        if (value === null) element.removeAttribute(name);
        else element.setAttribute(name, value);
      }
    }
    this.snapshots.clear();
  }
}

export interface OrbitalAbyss {
  moveTo(card: Element): boolean;
  clear(): void;
  dispose(): void;
}

function fixed(value: number): string {
  const rounded = Math.round(value * 100) / 100;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(2).replace(/0+$/, "");
}

function isHtmlElement(value: unknown, doc: Document): value is HTMLElement {
  const HtmlElement = doc.defaultView?.HTMLElement;
  return typeof HtmlElement === "function" && value instanceof HtmlElement;
}

function gameCards(container: Element): HTMLElement[] {
  const doc = container.ownerDocument;
  const list = container.getAttribute("role") === "list";
  const direct = [...container.children]
    .filter((child): child is HTMLElement => isHtmlElement(child, doc))
    .filter((child) => list
      ? child.getAttribute("role") === "listitem"
        && child.hasAttribute("data-id")
        && child.getAttribute("data-id") !== "GoToLibrary"
      : child.getAttribute("role") === "gridcell");
  if (direct.length || container.getAttribute("role") === "list") return direct;
  return [...container.querySelectorAll<HTMLElement>('[role="gridcell"]')]
    .filter((card) => card.closest('[role="grid"]') === container);
}

function orbitalContainer(card: Element): Element | null {
  return card.closest('[role="list"], [role="grid"]');
}

function numericStyle(value: string): number {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function defaultCaptionAction(appid: number): OrbitalCaptionAction {
  try {
    const sharedWindow = window as typeof window & {
      appStore?: {
        m_mapApps?: {
          get?: (appid: number) => {
            app_type?: unknown;
            local_per_client_data?: {
              installed?: unknown;
              is_available_on_current_platform?: unknown;
            };
          } | undefined;
        };
      };
    };
    const overview = sharedWindow.appStore?.m_mapApps?.get?.(appid);
    const installed = overview?.local_per_client_data?.installed;
    if (installed === true) return "play";
    if (installed === false) return "download";
    if (
      installed === undefined
      && overview?.app_type === 1
      && overview.local_per_client_data?.is_available_on_current_platform === true
    ) return "download";
  } catch {
    return null;
  }
  return null;
}

function captionAction(
  card: HTMLElement,
  resolveAction: NonNullable<OrbitalAbyssOptions["resolveAction"]>,
): OrbitalCaptionAction {
  const appid = appidFromCard(card);
  if (appid === null) return null;
  try {
    const action = resolveAction(appid);
    return action === "play" || action === "download" ? action : null;
  } catch {
    return null;
  }
}

function validAppid(raw: string | undefined): number | null {
  if (!raw || !/^\d+$/.test(raw)) return null;
  const appid = Number(raw);
  return Number.isSafeInteger(appid) && appid > 0 ? appid : null;
}

function appidFromCard(card: HTMLElement): number | null {
  const direct = validAppid(card.dataset.id);
  if (direct !== null) return direct;
  const assetAppids = new Set<number>();
  for (const image of card.querySelectorAll<HTMLImageElement>('img[src]')) {
    const match = image.getAttribute("src")?.match(/^\/assets\/(\d+)(?:\/|$)/);
    const appid = validAppid(match?.[1]);
    if (appid !== null) assetAppids.add(appid);
  }
  return assetAppids.size === 1 ? [...assetAppids][0] : null;
}

function normalizedPath(path: SVGPathElement): string {
  return (path.getAttribute("d") ?? "").replace(/\s+/g, " ").trim();
}

function inertActionSvg(svg: SVGSVGElement): boolean {
  const focusable = svg.getAttribute("focusable");
  return !svg.hasAttribute("role")
    && !svg.hasAttribute("tabindex")
    && (focusable === null || focusable === "false");
}

function decorativeActionShell(svg: SVGSVGElement, doc: Document): HTMLElement | null {
  const wrapper = svg.parentElement;
  if (
    !wrapper
    || !isHtmlElement(wrapper, doc)
    || wrapper.tagName !== "DIV"
    || wrapper.tabIndex >= 0
    || wrapper.childElementCount !== 1
    || wrapper.firstElementChild !== svg
    || wrapper.textContent?.trim()
    || wrapper.classList.contains("Focusable")
    || wrapper.classList.contains("gpfocus")
    || wrapper.classList.contains("gpfocuswithin")
  ) {
    return null;
  }
  const semanticAttribute = [...wrapper.attributes].some(({ name, value }) =>
    name === "role"
    || name === "tabindex"
    || name === "contenteditable"
    || name === "draggable" && value === "true"
    || name.startsWith("aria-")
    || name.startsWith("on"));
  return semanticAttribute ? null : wrapper;
}

function nativeActionElements(card: HTMLElement, action: OrbitalCaptionAction): Element[] {
  if (action === null) return [];
  const candidates: Array<{ visual: SVGSVGElement; shell: HTMLElement | null }> = [];
  for (const svg of card.querySelectorAll<SVGSVGElement>('svg[viewBox="0 0 36 36"]')) {
    if (!inertActionSvg(svg)) continue;
    const paths = [...svg.querySelectorAll<SVGPathElement>("path")].map(normalizedPath);
    if (action === "play" && paths.length === 1 && paths[0] === NATIVE_PLAY_PATH) {
      candidates.push({ visual: svg, shell: decorativeActionShell(svg, card.ownerDocument) });
    }
    if (
      action === "download"
      && paths.length === NATIVE_DOWNLOAD_PATHS.length
      && paths.every((path, index) => path === NATIVE_DOWNLOAD_PATHS[index])
    ) {
      const shell = decorativeActionShell(svg, card.ownerDocument);
      if (shell) candidates.push({ visual: svg, shell });
    }
  }
  if (candidates.length !== 1 || !card.contains(candidates[0].visual)) return [];
  const candidate = candidates[0];
  return candidate.shell ? [candidate.visual, candidate.shell] : [candidate.visual];
}

function labelledTitle(card: HTMLElement, doc: Document): string {
  const labelledBy = card.querySelector<HTMLElement>('[role="link"][aria-labelledby]')
    ?.getAttribute("aria-labelledby")
    ?.trim();
  if (!labelledBy) return "";
  for (const id of labelledBy.split(/\s+/)) {
    const labelled = doc.getElementById(id);
    if (labelled && card.contains(labelled)) {
      const text = labelled.textContent?.trim() ?? "";
      if (text) return text;
    }
  }
  return "";
}

function steamCopy(card: HTMLElement, doc: Document): SteamCopy | null {
  const view = doc.defaultView;
  const textLeaves = [...card.querySelectorAll<HTMLElement>("*")]
    .filter((element) => element.childElementCount === 0)
    .map((element) => ({ element, text: element.textContent?.trim() ?? "" }))
    .filter(({ text }) => text.length > 0 && text.length <= 160);
  const leaves = textLeaves
    .map(({ element, text }) => {
      const style = view?.getComputedStyle(element);
      return {
        element,
        fontSize: numericStyle(style?.fontSize ?? ""),
        fontWeight: numericStyle(style?.fontWeight ?? ""),
        text,
        visible: style?.display !== "none"
          && style?.visibility !== "hidden"
          && (style?.opacity !== "0" || element.dataset.pdcOrbitNativeCopy === "true"),
      };
    })
    .filter(({ visible }) => visible);
  const title = leaves
    .filter(({ fontSize, fontWeight }) => fontSize >= 16 && fontWeight >= 600)
    .sort((left, right) => right.fontSize - left.fontSize || right.fontWeight - left.fontWeight)[0];

  if (!title) {
    const link = card.querySelector<HTMLElement>('[role="link"]');
    const image = card.querySelector<HTMLImageElement>("img");
    const fallback = labelledTitle(card, doc)
      || link?.getAttribute("aria-label")?.trim()
      || image?.alt.trim();
    return fallback
      ? {
        title: fallback,
        titleElements: textLeaves.filter(({ text }) => text === fallback).map(({ element }) => element),
        meta: "",
        metaElements: [],
      }
      : null;
  }

  const titleIndex = leaves.indexOf(title);
  const meta = leaves.slice(titleIndex + 1)
    .find(({ fontSize, fontWeight }) => fontSize >= 10 && fontSize <= 15 && fontWeight >= 500);
  return {
    title: title.text,
    titleElements: textLeaves
      .filter(({ text }) => text === title.text)
      .map(({ element }) => element),
    meta: meta?.text ?? "",
    metaElements: meta
      ? textLeaves
        .filter(({ text }) => text === meta.text)
        .map(({ element }) => element)
      : [],
  };
}

function createCaptionIcon(doc: Document): SVGSVGElement {
  const svg = doc.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.dataset.pdcOrbitCaptionIcon = "true";
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  svg.setAttribute("hidden", "");
  svg.setAttribute("viewBox", "0 0 24 24");
  const frame = doc.createElementNS("http://www.w3.org/2000/svg", "circle");
  frame.dataset.pdcOrbitCaptionIconFrame = "true";
  frame.setAttribute("cx", "12");
  frame.setAttribute("cy", "12");
  frame.setAttribute("r", "10");
  const glyph = doc.createElementNS("http://www.w3.org/2000/svg", "path");
  glyph.dataset.pdcOrbitCaptionIconGlyph = "true";
  svg.append(frame, glyph);
  return svg;
}

function createStage(doc: Document, parent: HTMLElement): HTMLElement {
  const stage = doc.createElement("div");
  stage.id = STAGE_ID;
  stage.setAttribute("aria-hidden", "true");
  for (let index = 0; index < 3; index += 1) {
    const ring = doc.createElement("div");
    ring.dataset.pdcOrbitRing = String(index);
    stage.append(ring);
  }
  const horizon = doc.createElement("div");
  horizon.dataset.pdcOrbitHorizon = "true";
  stage.append(horizon);
  const caption = doc.createElement("div");
  caption.dataset.pdcOrbitCaption = "true";
  const title = doc.createElement("div");
  title.dataset.pdcOrbitCaptionTitle = "true";
  const icon = createCaptionIcon(doc);
  const label = doc.createElement("span");
  label.dataset.pdcOrbitCaptionLabel = "true";
  title.append(icon, label);
  const meta = doc.createElement("div");
  meta.dataset.pdcOrbitCaptionMeta = "true";
  caption.append(title, meta);
  stage.append(caption);
  parent.prepend(stage);
  return stage;
}

export function startOrbitalAbyss(doc: Document, options: OrbitalAbyssOptions = {}): OrbitalAbyss {
  const root = doc.documentElement;
  const view = doc.defaultView;
  const resolveAction = options.resolveAction ?? defaultCaptionAction;
  let stage: HTMLElement | null = null;
  let layout = new MutationLedger();
  let nativeActionLayout = new AttributeLedger();
  let rootState: string | null = null;
  let rootCaptured = false;
  let disposed = false;
  let captionFrame: number | null = null;
  let captionGeneration = 0;
  let captionObserver: MutationObserver | null = null;
  let observedCard: HTMLElement | null = null;

  const cancelCaptionSync = () => {
    captionGeneration += 1;
    captionObserver?.disconnect();
    captionObserver = null;
    observedCard = null;
    if (captionFrame !== null) view?.cancelAnimationFrame(captionFrame);
    captionFrame = null;
  };

  const markNativeCopy = (selectedCard: HTMLElement): SteamCopy | null => {
    const selectedCopy = steamCopy(selectedCard, doc);
    for (const element of selectedCopy?.titleElements ?? []) {
      layout.attribute(element, "data-pdc-orbit-native-copy", "true");
    }
    for (const element of selectedCopy?.metaElements ?? []) {
      layout.attribute(element, "data-pdc-orbit-native-copy", "true");
    }
    return selectedCopy;
  };

  const updateCaption = (selectedCard: HTMLElement): boolean => {
    if (!stage) return false;
    nativeActionLayout.restore();
    const selectedCopy = markNativeCopy(selectedCard);
    const caption = stage.querySelector<HTMLElement>('[data-pdc-orbit-caption="true"]');
    const captionLabel = stage.querySelector<HTMLElement>('[data-pdc-orbit-caption-label="true"]');
    const captionIcon = stage.querySelector<SVGSVGElement>('[data-pdc-orbit-caption-icon="true"]');
    const captionGlyph = captionIcon?.querySelector<SVGPathElement>('[data-pdc-orbit-caption-icon-glyph="true"]');
    const captionMeta = stage.querySelector<HTMLElement>('[data-pdc-orbit-caption-meta="true"]');
    if (!caption || !captionLabel || !captionIcon || !captionGlyph || !captionMeta) return false;
    caption.hidden = !selectedCopy;
    const title = selectedCopy?.title ?? "";
    const meta = selectedCopy?.meta ?? "";
    if (captionLabel.textContent !== title) captionLabel.textContent = title;
    if (captionMeta.textContent !== meta) captionMeta.textContent = meta;
    captionMeta.hidden = !selectedCopy?.meta;
    const action = captionAction(selectedCard, resolveAction);
    captionIcon.toggleAttribute("hidden", action === null);
    if (action === null) {
      captionIcon.removeAttribute("data-pdc-orbit-caption-action");
      captionGlyph.removeAttribute("d");
    } else {
      captionIcon.dataset.pdcOrbitCaptionAction = action;
      captionGlyph.setAttribute("d", action === "play"
        ? "M9 7.25L17 12 9 16.75Z"
        : "M12 5V14M8.5 10.5L12 14L15.5 10.5M7 18H17");
    }
    for (const element of nativeActionElements(selectedCard, action)) {
      nativeActionLayout.attribute(element, "data-pdc-orbit-native-action", "true");
    }
    return Boolean(selectedCopy?.titleElements.length);
  };

  const syncCaption = (selectedCard: HTMLElement, generation: number, framesLeft: number): void => {
    if (disposed || generation !== captionGeneration || updateCaption(selectedCard) || framesLeft <= 0) return;
    captionFrame = view?.requestAnimationFrame(() => {
      captionFrame = null;
      syncCaption(selectedCard, generation, framesLeft - 1);
    }) ?? null;
  };

  const observeCaption = (selectedCard: HTMLElement, generation: number): void => {
    const Observer = view?.MutationObserver;
    if (typeof Observer !== "function") return;
    let observer: MutationObserver | null = null;
    try {
      observer = new Observer(() => {
        if (disposed || generation !== captionGeneration || observedCard !== selectedCard) {
          return;
        }
        markNativeCopy(selectedCard);
        if (captionFrame !== null) return;
        captionFrame = view?.requestAnimationFrame(() => {
          captionFrame = null;
          if (disposed || generation !== captionGeneration || observedCard !== selectedCard) return;
          updateCaption(selectedCard);
        }) ?? null;
      });
      observer.observe(selectedCard, {
        attributes: true,
        attributeFilter: ["class", "d", "style", "viewBox"],
        childList: true,
        characterData: true,
        subtree: true,
      });
      captionObserver = observer;
      observedCard = selectedCard;
    } catch {
      observer?.disconnect();
      captionObserver?.disconnect();
      captionObserver = null;
      observedCard = null;
    }
  };

  const clear = () => {
    cancelCaptionSync();
    nativeActionLayout.restore();
    layout.restore();
    stage?.remove();
    stage = null;
    if (rootCaptured) {
      if (rootState === null) root.removeAttribute("data-pdc-orbit-active");
      else root.setAttribute("data-pdc-orbit-active", rootState);
    }
    rootState = null;
    rootCaptured = false;
  };

  return {
    moveTo(target) {
      if (disposed || !isHtmlElement(target, doc)) return false;
      const container = orbitalContainer(target);
      if (!isHtmlElement(container, doc)) {
        clear();
        return false;
      }
      const cards = gameCards(container);
      const card = target.matches('[role="listitem"], [role="gridcell"]')
        ? target
        : target.closest('[role="listitem"], [role="gridcell"]');
      const focusedIndex = card ? cards.indexOf(card as HTMLElement) : -1;
      if (focusedIndex < 0 || cards.length < 3) {
        clear();
        return false;
      }

      cancelCaptionSync();
      nativeActionLayout.restore();
      nativeActionLayout = new AttributeLedger();
      layout.restore();
      layout = new MutationLedger();
      if (!rootCaptured) {
        rootState = root.getAttribute("data-pdc-orbit-active");
        rootCaptured = true;
      }
      root.dataset.pdcOrbitActive = "true";
      const viewport = container.parentElement;
      if (!isHtmlElement(viewport, doc)) {
        clear();
        return false;
      }
      stage ??= createStage(doc, viewport);
      if (stage.parentElement !== viewport) viewport.prepend(stage);
      const phase = -focusedIndex * 45;
      stage.style.setProperty("--pdc-orbit-phase", `${phase}deg`);
      stage.style.setProperty("--pdc-orbit-phase-reverse", `${-phase + 24}deg`);
      stage.style.setProperty("--pdc-orbit-phase-offset", `${phase + 58}deg`);

      layout.attribute(container, "data-pdc-orbit-list", "true");
      layout.attribute(viewport, "data-pdc-orbit-viewport", "true");
      const main = container.closest("#Main");
      if (isHtmlElement(main, doc)) {
        layout.attribute(main, "data-pdc-orbit-main", "true");
        for (const shelf of main.querySelectorAll(".ReactVirtualized__Grid")) {
          if (shelf !== viewport && isHtmlElement(shelf, doc)) {
            layout.attribute(shelf, "data-pdc-orbit-suppressed", "true");
          }
        }
      }
      const footer = doc.getElementById("Footer");
      if (isHtmlElement(footer, doc)) {
        layout.attribute(footer, "data-pdc-orbit-footer", "true");
      }

      cards.forEach((candidate, index) => {
        const distance = index - focusedIndex;
        const visible = Math.abs(distance) <= VISIBLE_RADIUS;
        layout.attribute(candidate, "data-pdc-orbit-card", "true");
        layout.attribute(candidate, "data-pdc-orbit-visible", visible ? "true" : "false");
        if (!visible) return;

        const angle = (90 - distance * 45) * Math.PI / 180;
        const depth = (Math.sin(angle) + 1) / 2;
        const rearGateOffset = Math.abs(distance) === VISIBLE_RADIUS ? Math.sign(distance) * 8 : 0;
        const x = 50 + Math.cos(angle) * ORBIT_RADIUS_X + rearGateOffset;
        const y = ORBIT_CENTER_Y + Math.sin(angle) * ORBIT_RADIUS_Y;
        const scale = 0.42 + depth * 0.76;
        const opacity = 0.16 + depth * 0.84;
        layout.style(candidate, "--pdc-orbit-x", `${fixed(x)}%`);
        layout.style(candidate, "--pdc-orbit-y", `${fixed(y)}%`);
        layout.style(candidate, "--pdc-orbit-scale", fixed(scale));
        layout.style(candidate, "--pdc-orbit-opacity", fixed(opacity));
        layout.style(candidate, "--pdc-orbit-tilt", `${fixed(-Math.cos(angle) * 34)}deg`);
        layout.style(candidate, "--pdc-orbit-roll", `${fixed(-Math.cos(angle) * 5)}deg`);
        layout.style(candidate, "--pdc-orbit-z", String(Math.round(20 + depth * 80)));
        layout.attribute(candidate, "data-pdc-orbit-distance", String(distance));
        if (distance === 0) layout.attribute(candidate, "data-pdc-orbit-selected", "true");
      });
      const selectedCard = cards[focusedIndex];
      const generation = captionGeneration;
      observeCaption(selectedCard, generation);
      syncCaption(selectedCard, generation, CAPTION_SYNC_FRAMES);
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
