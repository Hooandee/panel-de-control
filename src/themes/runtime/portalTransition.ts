import type { ThemeRuntimeSurface } from "../types";
import { safeArtworkUrl } from "./artwork";

const PORTAL_ID = "pdc-obsidian-portal";

interface PortalTransitionOptions {
  setTimeout?(callback: () => void, delay: number): number;
  clearTimeout?(id: number): void;
  durationMs?: number;
  entryDurationMs?: number;
  entryTargetTimeoutMs?: number;
  fallbackDurationMs?: number;
  entryHandoffDelayMs?: number;
  exitTravelDurationMs?: number;
}

export interface PortalTransition {
  remember(artwork: string, rect: DOMRect): void;
  beginEntry(): void;
  completeEntry(): void;
  beginExit(): void;
  completeExit(): boolean;
  surfaceChanged(surface: ThemeRuntimeSurface | null): void;
  dispose(): void;
}

export function startPortalTransition(
  doc: Document,
  options: PortalTransitionOptions = {},
): PortalTransition {
  const win = doc.defaultView;
  const schedule = options.setTimeout ?? win?.setTimeout.bind(win);
  const cancel = options.clearTimeout ?? win?.clearTimeout.bind(win);
  const exitDurationMs = options.durationMs ?? 900;
  const entryDurationMs = options.entryDurationMs ?? 260;
  const entryTargetTimeoutMs = options.entryTargetTimeoutMs ?? 900;
  const fallbackDurationMs = options.fallbackDurationMs ?? 220;
  const entryHandoffDelayMs = options.entryHandoffDelayMs ?? 260;
  const exitTravelDurationMs = options.exitTravelDurationMs ?? 380;
  const root = doc.documentElement;
  const previousPhase = root.getAttribute("data-pdc-portal-phase");
  let artwork: string | null = null;
  let rect: DOMRect | null = null;
  let surface: ThemeRuntimeSurface | null = null;
  let host: HTMLElement | null = null;
  let direction: "entry" | "exit" | null = null;
  let timer = 0;
  let rememberedVersion = 0;
  let exitRememberedVersion = 0;
  let disposed = false;

  const viewport = () => ({
    height: Math.max(1, win?.innerHeight || doc.documentElement.clientHeight || 640),
    width: Math.max(1, win?.innerWidth || doc.documentElement.clientWidth || 1024),
  });
  const dockFor = (source: DOMRect) => {
    const { height: viewportHeight, width: viewportWidth } = viewport();
    const ratio = Math.max(.1, source.width / source.height);
    const width = Math.min(viewportWidth * .235, 252, viewportHeight * .64 * ratio);
    const height = width / ratio;
    return {
      height,
      width,
      x: viewportWidth * .185,
      y: viewportHeight * .49,
    };
  };

  const removeHost = () => {
    if (timer && cancel) cancel(timer);
    timer = 0;
    host?.remove();
    host = null;
    direction = null;
    if (previousPhase === null) root.removeAttribute("data-pdc-portal-phase");
    else root.setAttribute("data-pdc-portal-phase", previousPhase);
  };
  const scheduleRemoval = (delay: number) => {
    if (!schedule) return;
    if (timer && cancel) cancel(timer);
    timer = schedule(removeHost, delay);
  };
  const reveal = (state: "entry" | "exit", duration: number) => {
    if (!host || direction !== state) return;
    if (state === "entry") host.dataset.pdcPortalEntryState = "revealing";
    else host.dataset.pdcPortalExitState = "revealing";
    host.style.setProperty("--pdc-portal-reveal-duration", `${duration}ms`);
    host.style.opacity = "0";
    scheduleRemoval(duration);
  };
  const beginEntryFallback = () => {
    timer = 0;
    if (!host || direction !== "entry" || host.dataset.pdcPortalEntryState !== "covering") return;
    reveal("entry", fallbackDurationMs);
  };
  const beginEntryReveal = () => {
    timer = 0;
    if (!host || direction !== "entry" || host.dataset.pdcPortalEntryState !== "docked") return;
    reveal("entry", entryDurationMs);
  };
  const mount = (nextDirection: "entry" | "exit") => {
    if (!artwork || !rect || !doc.body || !schedule) return;
    removeHost();
    if (doc.getElementById(PORTAL_ID)) return;
    direction = nextDirection;
    root.dataset.pdcPortalPhase = nextDirection;
    host = doc.createElement("div");
    host.id = PORTAL_ID;
    host.dataset.pdcPortalDirection = nextDirection;
    if (nextDirection === "entry") host.dataset.pdcPortalEntryState = "covering";
    else host.dataset.pdcPortalExitState = "covering";
    host.setAttribute("aria-hidden", "true");
    host.style.pointerEvents = "none";
    host.style.opacity = "1";
    host.style.setProperty("--pdc-portal-artwork", `url(${JSON.stringify(artwork)})`);
    const dock = dockFor(rect);
    const sourceX = nextDirection === "entry" ? rect.left + rect.width / 2 : dock.x;
    const sourceY = nextDirection === "entry" ? rect.top + rect.height / 2 : dock.y;
    const sourceWidth = nextDirection === "entry" ? rect.width : dock.width;
    const sourceHeight = nextDirection === "entry" ? rect.height : dock.height;
    host.style.setProperty("--pdc-portal-x", `${Math.round(sourceX)}px`);
    host.style.setProperty("--pdc-portal-y", `${Math.round(sourceY)}px`);
    host.style.setProperty("--pdc-portal-width", `${Math.max(1, Math.round(sourceWidth))}px`);
    host.style.setProperty("--pdc-portal-height", `${Math.max(1, Math.round(sourceHeight))}px`);
    host.style.setProperty("--pdc-portal-dock-x", `${Math.round(dock.x)}px`);
    host.style.setProperty("--pdc-portal-dock-y", `${Math.round(dock.y)}px`);
    host.style.setProperty("--pdc-portal-dock-dx", `${Math.round(dock.x - sourceX)}px`);
    host.style.setProperty("--pdc-portal-dock-dy", `${Math.round(dock.y - sourceY)}px`);
    host.style.setProperty("--pdc-portal-dock-scale", `${dock.width / Math.max(1, sourceWidth)}`);
    host.style.setProperty("--pdc-portal-entry-duration", `${entryDurationMs}ms`);
    host.style.setProperty("--pdc-portal-fallback-duration", `${fallbackDurationMs}ms`);
    const artworkLayer = doc.createElement("div");
    artworkLayer.dataset.pdcPortalArtwork = "true";
    host.append(artworkLayer);
    doc.body.append(host);
    if (nextDirection === "entry") {
      timer = schedule(beginEntryFallback, entryTargetTimeoutMs);
    } else {
      timer = schedule(removeHost, exitDurationMs);
    }
  };
  const onVisibilityChange = () => removeHost();
  doc.addEventListener("visibilitychange", onVisibilityChange);

  return {
    remember(nextArtwork, nextRect) {
      if (disposed) return;
      const nextArtworkUrl = safeArtworkUrl(nextArtwork);
      const validRect = [nextRect.left, nextRect.top, nextRect.width, nextRect.height]
        .every(Number.isFinite)
        && nextRect.width > 0
        && nextRect.height > 0;
      artwork = nextArtworkUrl && validRect ? nextArtworkUrl : null;
      rect = artwork ? nextRect : null;
      if (rect) rememberedVersion += 1;
    },
    beginEntry() {
      if (disposed || (surface !== "library" && surface !== "library-grid")) return;
      mount("entry");
    },
    completeEntry() {
      if (disposed || host?.dataset.pdcPortalEntryState !== "covering") return;
      if (timer && cancel) cancel(timer);
      host.dataset.pdcPortalEntryState = "docked";
      timer = schedule?.(beginEntryReveal, entryHandoffDelayMs) ?? 0;
    },
    beginExit() {
      if (disposed || surface !== "game-details") return;
      exitRememberedVersion = rememberedVersion;
      mount("exit");
    },
    completeExit() {
      if (
        disposed
        || !host
        || !rect
        || host.dataset.pdcPortalExitState !== "covering"
        || rememberedVersion <= exitRememberedVersion
        || (surface !== "library" && surface !== "library-grid")
      ) return false;
      const dock = dockFor(rect);
      const targetX = rect.left + rect.width / 2;
      const targetY = rect.top + rect.height / 2;
      host.style.setProperty("--pdc-portal-target-x", `${Math.round(targetX)}px`);
      host.style.setProperty("--pdc-portal-target-y", `${Math.round(targetY)}px`);
      host.style.setProperty("--pdc-portal-target-dx", `${Math.round(targetX - dock.x)}px`);
      host.style.setProperty("--pdc-portal-target-dy", `${Math.round(targetY - dock.y)}px`);
      host.style.setProperty("--pdc-portal-target-scale", `${rect.width / Math.max(1, dock.width)}`);
      host.style.setProperty("--pdc-portal-exit-duration", `${exitTravelDurationMs}ms`);
      host.dataset.pdcPortalExitState = "returning";
      scheduleRemoval(exitTravelDurationMs);
      return true;
    },
    surfaceChanged(nextSurface) {
      if (disposed) return;
      const fromLibrary = surface === "library" || surface === "library-grid";
      const entersDetails = nextSurface === "game-details" && surface !== "game-details";
      surface = nextSurface;
      if (entersDetails && fromLibrary && direction !== "entry") {
        mount("entry");
        return;
      }
      if (
        nextSurface === null
        || (nextSurface !== "game-details" && nextSurface !== "library" && nextSurface !== "library-grid")
      ) {
        removeHost();
        return;
      }
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      doc.removeEventListener("visibilitychange", onVisibilityChange);
      removeHost();
      artwork = null;
      rect = null;
      rememberedVersion = 0;
      exitRememberedVersion = 0;
      surface = null;
    },
  };
}
