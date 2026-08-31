import type { ThemeRuntimeSurface } from "../types";
import type { ThemeRuntimeModule } from "./runtimeManager";
import { hasSteamSurfaceSentinel } from "./surfaceDetector";
import { startSteamSurfaceSession } from "./surfaceSession";

export const GALLERY_SURFACE_MARKERS = {
  library: "/* pdc-gallery-surface: library */",
  "library-grid": "/* pdc-gallery-surface: library-grid */",
  "game-details": "/* pdc-gallery-surface: game-details */",
  settings: "/* pdc-gallery-surface: settings */",
} as const satisfies Record<ThemeRuntimeSurface, string>;

export const GALLERY_FEATURE_MARKERS = {
  downloads: "/* pdc-gallery-feature: downloads:v1 */",
  media: "/* pdc-gallery-feature: media:v1 */",
} as const;

type GalleryFeature = keyof typeof GALLERY_FEATURE_MARKERS;

const GALLERY_SHARED_MARKER = "/* pdc-gallery-runtime: shared */";
const GALLERY_MARKER_PREFIX = "/* pdc-gallery-surface:";
const GALLERY_FEATURE_MARKER_PREFIX = "/* pdc-gallery-feature:";
const GALLERY_SURFACES = Object.keys(GALLERY_SURFACE_MARKERS) as ThemeRuntimeSurface[];
const GALLERY_FEATURES = Object.keys(GALLERY_FEATURE_MARKERS) as GalleryFeature[];
const GALLERY_SURFACE_SENTINELS = [
  '[role="listitem"][data-id="GoToLibrary"]',
  '[role="tab"][id$="AllGames"]',
  '[role="tab"][id$="Soundtracks"]',
  '[role="tab"][aria-controls$="GameInfo_Content"]',
  '[id*="/settings/"][role="tab"]',
] as const;
const GALLERY_SURFACE_SENTINEL_SELECTOR = GALLERY_SURFACE_SENTINELS.join(",");
const GALLERY_FEATURE_MUTATION_SELECTOR = [
  '[data-rbd-droppable-context-id][role="list"]',
  '[role="grid"]',
  ".OpenedItemContainer",
  ".FullModalOverlay",
  'img[src*="steamusercontent.com/ugc/"]',
].join(",");

interface ObserverLike {
  observe(target: Node, options?: MutationObserverInit): void;
  disconnect(): void;
}

interface GalleryRuntimeDependencies {
  startSurfaceSession?: typeof startSteamSurfaceSession;
  createObserver?(callback: MutationCallback): ObserverLike;
  requestAnimationFrame?(callback: FrameRequestCallback): number;
  cancelAnimationFrame?(handle: number): void;
  setTimeout?(callback: () => void, delay: number): number;
  clearTimeout?(handle: number): void;
}

interface ManagedStyleSheet {
  style: HTMLStyleElement;
  sheet: CSSStyleSheet;
  originalDisabled: boolean;
}

interface ManagedSheet extends ManagedStyleSheet {
  surface: ThemeRuntimeSurface;
  shared: boolean;
}

interface ManagedFeatureSheet extends ManagedStyleSheet {
  feature: GalleryFeature;
}

function restoreManagedSheets(entries: Iterable<ManagedStyleSheet>): void {
  for (const managed of entries) {
    if (managed.sheet.disabled !== managed.originalDisabled) {
      managed.sheet.disabled = managed.originalDisabled;
    }
  }
}

function pruneManagedSheets<T extends ManagedStyleSheet>(entries: Map<CSSStyleSheet, T>): void {
  for (const [sheet, managed] of entries) {
    if (!managed.style.isConnected || managed.style.sheet !== sheet) entries.delete(sheet);
  }
}

function hasGalleryFeatureSentinel(doc: Document, feature: GalleryFeature): boolean {
  if (feature === "downloads") {
    return Boolean(doc.querySelector('#Main [data-rbd-droppable-context-id][role="list"]'));
  }
  if (doc.querySelector("#Main .OpenedItemContainer")) return true;
  if (doc.querySelector(
    '#GamepadUI_Full_Root .FullModalOverlay > .ModalOverlayContent.active img[src*="steamusercontent.com/ugc/"]',
  )) return true;
  if (
    !hasSteamSurfaceSentinel(doc, "library-grid")
    && doc.querySelector(
      '#Main [role="grid"] > [role="row"] [role="button"] img[src*="steamusercontent.com/ugc/"]',
    )
  ) return true;
  return Boolean(doc.querySelector(
    "#Main div:has(> :first-child:not([role]) + [role=\"button\"]):has(> [role=\"button\"]:nth-child(10))",
  ));
}

function mutationsTouchGallerySurface(records: readonly MutationRecord[]): boolean {
  const touchesSentinel = (node: Node) => {
    if (node.nodeType !== 1) return false;
    const element = node as Element;
    return element.matches(GALLERY_SURFACE_SENTINEL_SELECTOR)
      || Boolean(element.querySelector(GALLERY_SURFACE_SENTINEL_SELECTOR));
  };
  return records.some((record) => (
    [...record.addedNodes, ...record.removedNodes].some(touchesSentinel)
  ));
}

function mutationsTouchGalleryFeature(records: readonly MutationRecord[]): boolean {
  const touchesSentinel = (node: Node) => {
    if (node.nodeType !== 1) return false;
    const element = node as Element;
    return element.matches(GALLERY_FEATURE_MUTATION_SELECTOR)
      || Boolean(element.querySelector(GALLERY_FEATURE_MUTATION_SELECTOR));
  };
  return records.some((record) => (
    [...record.addedNodes, ...record.removedNodes].some(touchesSentinel)
  ));
}

class GallerySheetIsolation {
  private readonly sheets = new Map<CSSStyleSheet, ManagedSheet>();
  private readonly featureSheets = new Map<CSSStyleSheet, ManagedFeatureSheet>();
  private activeSurface: ThemeRuntimeSurface | null = null;

  constructor(private readonly doc: Document) {}

  updateSurface(surface: ThemeRuntimeSurface | null): void {
    this.activeSurface = surface;
    this.reconcile();
  }

  reconcile(): void {
    this.prune();
    const indexed = new Map<ThemeRuntimeSurface, ManagedSheet[]>();
    const indexedFeatures = new Map<GalleryFeature, ManagedFeatureSheet[]>();
    let invalidSurfaces = false;
    const invalidFeatures = new Set<GalleryFeature>();

    for (const style of this.doc.head?.querySelectorAll<HTMLStyleElement>("style.css-loader-style") ?? []) {
      const text = style.textContent ?? "";
      const surface = GALLERY_SURFACES.find((candidate) => (
        text.startsWith(GALLERY_SURFACE_MARKERS[candidate])
      ));
      if (!surface) {
        if (text.startsWith(GALLERY_MARKER_PREFIX)) invalidSurfaces = true;
        const feature = GALLERY_FEATURES.find((candidate) => (
          text.startsWith(GALLERY_FEATURE_MARKERS[candidate])
        ));
        if (!feature) {
          if (text.startsWith(GALLERY_FEATURE_MARKER_PREFIX)) {
            const versionedFeature = GALLERY_FEATURES.find((candidate) => (
              text.startsWith(`/* pdc-gallery-feature: ${candidate}:`)
            ));
            if (versionedFeature) invalidFeatures.add(versionedFeature);
          }
          continue;
        }
        const sheet = style.sheet;
        if (!sheet) {
          invalidFeatures.add(feature);
          continue;
        }
        let managed = this.featureSheets.get(sheet);
        if (!managed) {
          managed = {
            style,
            sheet,
            feature,
            originalDisabled: sheet.disabled,
          };
          this.featureSheets.set(sheet, managed);
        } else {
          managed.style = style;
          managed.feature = feature;
        }
        const entries = indexedFeatures.get(feature) ?? [];
        entries.push(managed);
        indexedFeatures.set(feature, entries);
        continue;
      }
      const sheet = style.sheet;
      if (!sheet) {
        invalidSurfaces = true;
        continue;
      }
      let managed = this.sheets.get(sheet);
      if (!managed) {
        managed = {
          style,
          sheet,
          surface,
          shared: text.includes(GALLERY_SHARED_MARKER),
          originalDisabled: sheet.disabled,
        };
        this.sheets.set(sheet, managed);
      } else {
        managed.style = style;
        managed.surface = surface;
        managed.shared = text.includes(GALLERY_SHARED_MARKER);
      }
      const entries = indexed.get(surface) ?? [];
      entries.push(managed);
      indexed.set(surface, entries);
    }

    if (GALLERY_SURFACES.some((surface) => indexed.get(surface)?.length !== 1)) {
      invalidSurfaces = true;
    }
    for (const feature of GALLERY_FEATURES) {
      if (indexedFeatures.get(feature)?.length !== 1) invalidFeatures.add(feature);
    }
    const present = new Set(GALLERY_SURFACES.filter((surface) => (
      hasSteamSurfaceSentinel(this.doc, surface)
    )));
    const presentFeatures = new Set(GALLERY_FEATURES.filter((feature) => (
      hasGalleryFeatureSentinel(this.doc, feature)
    )));
    const knownSurface = Boolean(this.activeSurface && present.has(this.activeSurface));
    const knownContext = knownSurface || presentFeatures.size > 0;

    if (invalidSurfaces || !knownContext) {
      this.restoreRoutes();
    } else {
      for (const managed of this.sheets.values()) {
        const disabled = managed.originalDisabled
          || (!managed.shared && !present.has(managed.surface));
        if (managed.sheet.disabled !== disabled) managed.sheet.disabled = disabled;
      }
    }

    if (!knownContext) {
      this.restoreFeatures();
    } else {
      for (const managed of this.featureSheets.values()) {
        if (invalidFeatures.has(managed.feature)) {
          if (managed.sheet.disabled !== managed.originalDisabled) {
            managed.sheet.disabled = managed.originalDisabled;
          }
          continue;
        }
        const requiredByDetails = managed.feature === "media"
          && this.activeSurface === "game-details";
        const disabled = managed.originalDisabled
          || (!presentFeatures.has(managed.feature) && !requiredByDetails);
        if (managed.sheet.disabled !== disabled) managed.sheet.disabled = disabled;
      }
    }
  }

  restore(): void {
    this.restoreRoutes();
    this.restoreFeatures();
  }

  private restoreRoutes(): void {
    restoreManagedSheets(this.sheets.values());
  }

  private restoreFeatures(): void {
    restoreManagedSheets(this.featureSheets.values());
  }

  dispose(): void {
    this.restore();
    this.sheets.clear();
    this.featureSheets.clear();
  }

  private prune(): void {
    pruneManagedSheets(this.sheets);
    pruneManagedSheets(this.featureSheets);
  }
}

interface GalleryRuntimeOwner {
  refs: number;
  stop(): void;
}

const galleryRuntimeOwners = new WeakMap<Document, GalleryRuntimeOwner>();

function mountGalleryRuntime(
  doc: Document,
  dependencies: GalleryRuntimeDependencies = {},
): () => void {
  const root = doc.documentElement;
  const previousRuntime = root.getAttribute("data-pdc-theme-runtime");
  const previousGridMotion = root.getAttribute("data-pdc-gallery-grid-motion");
  const isolation = new GallerySheetIsolation(doc);
  const startSurfaceSession = dependencies.startSurfaceSession ?? startSteamSurfaceSession;
  const win = doc.defaultView;
  const createObserver = dependencies.createObserver
    ?? (win && typeof win.MutationObserver === "function"
      ? (callback: MutationCallback) => new win.MutationObserver(callback)
      : undefined);
  const requestFrame = dependencies.requestAnimationFrame
    ?? win?.requestAnimationFrame.bind(win);
  const cancelFrame = dependencies.cancelAnimationFrame
    ?? win?.cancelAnimationFrame.bind(win);
  const scheduleTimeout = dependencies.setTimeout ?? win?.setTimeout.bind(win);
  const cancelTimeout = dependencies.clearTimeout ?? win?.clearTimeout.bind(win);
  let stopSurfaceSession: (() => void) | null = null;
  let headObserver: ObserverLike | null = null;
  let frame = 0;
  let stopped = false;
  let activeSurface: ThemeRuntimeSurface | null = null;
  let gridMotionTimer: number | null = null;

  const reconcileSafely = () => {
    try {
      isolation.reconcile();
    } catch {
      isolation.restore();
    }
  };

  const restoreRuntimeOwner = () => {
    if (previousRuntime === null) root.removeAttribute("data-pdc-theme-runtime");
    else root.setAttribute("data-pdc-theme-runtime", previousRuntime);
  };
  const restoreGridMotion = () => {
    if (gridMotionTimer !== null && cancelTimeout) cancelTimeout(gridMotionTimer);
    gridMotionTimer = null;
    if (previousGridMotion === null) root.removeAttribute("data-pdc-gallery-grid-motion");
    else root.setAttribute("data-pdc-gallery-grid-motion", previousGridMotion);
  };
  const settleGridMotion = () => {
    if (gridMotionTimer !== null && cancelTimeout) cancelTimeout(gridMotionTimer);
    gridMotionTimer = null;
    root.removeAttribute("data-pdc-gallery-grid-motion");
  };
  const boundGridMutation = (records: readonly MutationRecord[]) => {
    if (
      activeSurface !== "library-grid"
      || !scheduleTimeout
      || !cancelTimeout
      || !records.some((record) => record.addedNodes.length || record.removedNodes.length)
    ) return;
    if (root.dataset.pdcGalleryGridMotion !== "busy") {
      root.dataset.pdcGalleryGridMotion = "busy";
    }
    if (gridMotionTimer !== null) cancelTimeout(gridMotionTimer);
    gridMotionTimer = scheduleTimeout(() => {
      gridMotionTimer = null;
      root.removeAttribute("data-pdc-gallery-grid-motion");
    }, 180);
  };
  const stop = () => {
    if (stopped) return;
    stopped = true;
    if (frame && cancelFrame) cancelFrame(frame);
    frame = 0;
    headObserver?.disconnect();
    headObserver = null;
    stopSurfaceSession?.();
    stopSurfaceSession = null;
    isolation.dispose();
    restoreGridMotion();
    restoreRuntimeOwner();
  };
  const scheduleReconcile = () => {
    if (stopped || frame || !requestFrame) return;
    frame = requestFrame(() => {
      frame = 0;
      if (!stopped) reconcileSafely();
    });
  };

  try {
    root.dataset.pdcThemeRuntime = "gallery";
    stopSurfaceSession = startSurfaceSession({
      doc,
      onSurface: (surface) => {
        try {
          activeSurface = surface;
          if (surface !== "library-grid") settleGridMotion();
          isolation.updateSurface(surface);
        } catch {
          isolation.restore();
        }
      },
      onBeforeRefresh: (records) => {
        boundGridMutation(records);
        if (
          mutationsTouchGallerySurface(records)
          || mutationsTouchGalleryFeature(records)
        ) reconcileSafely();
      },
    });
    if (createObserver && requestFrame && cancelFrame && doc.head) {
      headObserver = createObserver(scheduleReconcile);
      headObserver.observe(doc.head, {
        childList: true,
        subtree: true,
        characterData: true,
      });
    }
    return stop;
  } catch (error) {
    stop();
    throw error;
  }
}

function acquireGalleryRuntime(
  doc: Document,
  dependencies: GalleryRuntimeDependencies,
): () => void {
  let owner = galleryRuntimeOwners.get(doc);
  if (owner) {
    owner.refs += 1;
  } else {
    owner = {
      refs: 1,
      stop: mountGalleryRuntime(doc, dependencies),
    };
    galleryRuntimeOwners.set(doc, owner);
  }
  let released = false;
  return () => {
    if (released) return;
    released = true;
    if (galleryRuntimeOwners.get(doc) !== owner) return;
    owner.refs -= 1;
    if (owner.refs > 0) return;
    galleryRuntimeOwners.delete(doc);
    owner.stop();
  };
}

export function createGalleryRuntime(
  doc: Document,
  dependencies: GalleryRuntimeDependencies = {},
): ThemeRuntimeModule {
  return {
    id: "gallery",
    mount: () => acquireGalleryRuntime(doc, dependencies),
  };
}
