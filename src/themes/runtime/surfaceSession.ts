import { detectSteamSurface, hasSteamSurfaceSentinel } from "./surfaceDetector";
import type { ThemeRuntimeSurface } from "../types";

interface ObserverLike {
  observe(target: Node, options?: MutationObserverInit): void;
  disconnect(): void;
}

interface SteamSurfaceSessionOptions {
  doc: Document;
  onSurface(surface: ThemeRuntimeSurface | null, main: Element | null): void;
  onBeforeRefresh?(records: readonly MutationRecord[]): void;
  createObserver?(callback: MutationCallback): ObserverLike;
  requestAnimationFrame?(callback: FrameRequestCallback): number;
  cancelAnimationFrame?(handle: number): void;
}

export function startSteamSurfaceSession({
  doc,
  onSurface,
  onBeforeRefresh,
  createObserver,
  requestAnimationFrame,
  cancelAnimationFrame,
}: SteamSurfaceSessionOptions): () => void {
  const win = doc.defaultView;
  const makeObserver = createObserver
    ?? (win && typeof win.MutationObserver === "function"
      ? (callback: MutationCallback) => new win.MutationObserver(callback)
      : undefined);
  const scheduleFrame = requestAnimationFrame ?? win?.requestAnimationFrame.bind(win);
  const cancelFrame = cancelAnimationFrame ?? win?.cancelAnimationFrame.bind(win);
  if (!makeObserver || !scheduleFrame || !cancelFrame) return () => {};

  let activeMain: Element | null = null;
  let activeSurface: ThemeRuntimeSurface | null = null;
  let overlapSource: ThemeRuntimeSurface | null = null;
  let overlapTarget: ThemeRuntimeSurface | null = null;
  let bound = false;
  let mainObserver: ObserverLike | null = null;
  let boundaryObserver: ObserverLike | null = null;
  let frame = 0;
  let stopped = false;

  const disconnectObservers = () => {
    mainObserver?.disconnect();
    boundaryObserver?.disconnect();
    mainObserver = null;
    boundaryObserver = null;
  };
  const refresh = () => {
    frame = 0;
    if (stopped) return;
    const nextMain = doc.getElementById("Main");
    if (!bound || nextMain !== activeMain) {
      disconnectObservers();
      activeMain = nextMain;
      bound = true;
      if (activeMain) {
        mainObserver = makeObserver(scheduleRefresh);
        boundaryObserver = makeObserver(scheduleRefresh);
        mainObserver.observe(activeMain, { childList: true, subtree: true });
        if (activeMain.parentElement) {
          boundaryObserver.observe(activeMain.parentElement, { childList: true });
        }
      } else if (doc.body) {
        boundaryObserver = makeObserver(scheduleRefresh);
        boundaryObserver.observe(doc.body, { childList: true, subtree: true });
      }
    }
    if (
      overlapSource
      && overlapTarget
      && hasSteamSurfaceSentinel(doc, overlapSource)
      && hasSteamSurfaceSentinel(doc, overlapTarget)
    ) {
      activeSurface = overlapTarget;
    } else {
      overlapSource = null;
      overlapTarget = null;
      const detectedSurface = detectSteamSurface(doc, activeSurface);
      if (
        activeSurface
        && detectedSurface
        && detectedSurface !== activeSurface
        && hasSteamSurfaceSentinel(doc, activeSurface)
        && hasSteamSurfaceSentinel(doc, detectedSurface)
      ) {
        overlapSource = activeSurface;
        overlapTarget = detectedSurface;
      }
      activeSurface = detectedSurface;
    }
    onSurface(activeSurface, activeMain);
  };
  const scheduleRefresh: MutationCallback = (records) => {
    if (stopped) return;
    try {
      onBeforeRefresh?.(records);
    } catch {}
    if (!frame) frame = scheduleFrame(refresh);
  };

  try {
    refresh();
  } catch (error) {
    stopped = true;
    if (frame) cancelFrame(frame);
    disconnectObservers();
    throw error;
  }
  return () => {
    if (stopped) return;
    stopped = true;
    if (frame) cancelFrame(frame);
    disconnectObservers();
  };
}
