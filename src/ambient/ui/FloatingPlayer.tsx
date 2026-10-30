import { findSP, getGamepadNavigationTrees } from "@decky/ui";
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type FC, type PointerEvent as ReactPointerEvent } from "react";
import { createPortal } from "react-dom";

import { useI18n } from "../../i18n";
import { canDrawOverGames, OverGameComposition, UIComposition } from "../../platform/overGameComposition";
import { theme } from "../../theme";
import { CONTROL_BUTTONS, CONTROL_IDLE_MS, GamepadButton, controlAction, keyToButton } from "../core/overlayControl";
import { captureButtons } from "../../platform/buttonCapture";
import { onQamLeftEdge, qamPanelWidth, subscribeQamSurface, type QamSurface } from "../../platform/qamSurface";
import {
  cardWidth,
  fullscreenVideoBounds,
  clampPosition,
  cornerPosition,
  nearestCorner,
  springStep,
  type Point,
  type Size,
} from "../core/overlayLayout";
import type { OverlayCorner } from "../core/types";
import { NowPlaying } from "./NowPlaying";
import { VideoCard } from "./VideoCard";
import { useAmbient } from "./useAmbient";
import { useLibraryDock } from "./libraryDock";
import { focusLibraryElement } from "./libraryNavigation";

const HOST_ID = "pdc-ambient-floating";
const PEEK_MS = 6000;
const DRAG_THRESHOLD_PX = 6;
const REVEAL_MS = 3000;
const MIN_SCALE = 20;
const MAX_SCALE = 70;
const SCALE_STEP = 10;

function mainWindow(): Window | null {
  try {
    return findSP() ?? null;
  } catch {
    return null;
  }
}

function useViewport(view: Window | null): Size | null {
  const [size, setSize] = useState<Size | null>(() => (view ? { width: view.innerWidth, height: view.innerHeight } : null));
  useEffect(() => {
    if (!view) return;
    const update = () => setSize({ width: view.innerWidth, height: view.innerHeight });
    update();
    view.addEventListener("resize", update);
    return () => view.removeEventListener("resize", update);
  }, [view]);
  return size;
}

interface Drag {
  pointer: number;
  start: Point;
  grab: Point;
  moved: boolean;
}

/**
 * One floating card over games: the mini player, holding the video when it is on. It is dragged
 * by touch and settles into the nearest corner. It lives in Steam's main window, which Steam's
 * notification composition keeps drawn over the game; the video is Steam's native browser view,
 * kept exactly over the card's video slot.
 */
const ENTRY_GUARD_MS = 400;

export const FloatingPlayer: FC = () => {
  const { runtime, snapshot } = useAmbient();
  const { t } = useI18n();
  const dock = useLibraryDock();
  const [dockBounds, setDockBounds] = useState<DOMRect | null>(null);
  const [view] = useState(mainWindow);
  const viewport = useViewport(view);
  const [host, setHost] = useState<HTMLDivElement | null>(null);
  const [surface, setSurface] = useState<QamSurface | null>(null);
  const [peekUntil, setPeekUntil] = useState(0);
  const [cardHeight, setCardHeight] = useState(0);
  const [position, setPosition] = useState<Point | null>(null);
  const [corner, setCorner] = useState<OverlayCorner | null>(null);
  const card = useRef<HTMLDivElement | null>(null);
  const drag = useRef<Drag | null>(null);
  const frame = useRef<number | null>(null);

  useEffect(() => subscribeQamSurface(setSurface), []);
  useEffect(() => runtime?.markFloatingMounted(), [runtime]);

  useEffect(() => {
    const doc = view?.document;
    if (!doc?.body) return;
    doc.getElementById(HOST_ID)?.remove();
    const node = doc.createElement("div");
    node.id = HOST_ID;
    doc.body.appendChild(node);
    setHost(node);
    return () => {
      node.remove();
      setHost(null);
    };
  }, [view]);

  const player = snapshot?.player;
  const music = snapshot?.state?.settings.music;
  const trackKey = player?.track ? `${player.track.id}|${player.track.title}` : "";
  const playing = player?.status === "playing";
  const inGame = !!snapshot?.inGame;
  const qamOpen = !!surface?.visible;
  const videoOpen = !!player?.video && player.picture !== false;
  const video = videoOpen && !snapshot?.videoCollapsed;
  const libraryOpen = !!snapshot?.libraryOpen || !!snapshot?.libraryShown;
  const dockElement = libraryOpen && dock?.runtime === runtime ? dock.element : null;
  const fullscreen = video && !!snapshot?.videoFullscreen;
  const docked = !!dockElement && !fullscreen;
  const controlling = (!libraryOpen || fullscreen) && !!snapshot?.overlayControl;
  const [lastInput, setLastInput] = useState(0);

  useEffect(() => {
    if (!trackKey || !playing || qamOpen) return;
    const until = Date.now() + PEEK_MS;
    setPeekUntil(until);
    const timer = setTimeout(() => setPeekUntil((current) => (current === until ? 0 : current)), PEEK_MS);
    return () => clearTimeout(timer);
  }, [trackKey, playing, qamOpen]);

  const mode = music?.overlay ?? "peek";
  const pillWanted = !qamOpen && (mode === "always" || (mode === "peek" && peekUntil > Date.now()));
  const videoRunning = video && (playing || player?.status === "loading" || player?.status === "retrying");
  const visible = !!player?.track && (libraryOpen ? !!dockElement : videoRunning || pillWanted || controlling);
  const rightInset = qamOpen && surface ? qamPanelWidth(surface.document) ?? 0 : 0;
  const normalWidth = viewport ? cardWidth(viewport, rightInset, video, music?.videoScale ?? 40) : 0;
  const width = fullscreen && viewport ? viewport.width : docked ? dockBounds?.width ?? 0 : normalWidth;
  const videoHeight = fullscreen && viewport ? viewport.height : video ? Math.round((width * 9) / 16) : 0;
  const settled = corner ?? music?.overlayCorner ?? "top-right";
  const size: Size = { width: normalWidth, height: video ? Math.round(normalWidth * 9 / 16) : cardHeight };
  const target = !fullscreen && viewport && cardHeight ? cornerPosition(settled, size, viewport, rightInset) : null;

  useLayoutEffect(() => {
    if (!host || !view) return;
    view.document.body.appendChild(host);
    if (!dockElement) { setDockBounds(null); return; }
    const measure = () => setDockBounds(dockElement.getBoundingClientRect());
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(dockElement);
    view.addEventListener("resize", measure);
    view.document.addEventListener("scroll", measure, true);
    return () => {
      observer.disconnect();
      view.removeEventListener("resize", measure);
      view.document.removeEventListener("scroll", measure, true);
      view.document.body.appendChild(host);
    };
  }, [host, view, dockElement, docked]);

  useLayoutEffect(() => {
    const node = card.current;
    if (!node) return;
    const measure = () => setCardHeight(node.offsetHeight);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [visible, host]);

  useEffect(() => {
    if (music?.overlayCorner && !drag.current) setCorner(null);
  }, [music?.overlayCorner]);

  const cancelFrame = useCallback(() => {
    if (frame.current !== null) view?.cancelAnimationFrame(frame.current);
    frame.current = null;
  }, [view]);

  useEffect(() => {
    if (fullscreen || libraryOpen) { cancelFrame(); return; }
    if (!target || drag.current || !view) return;
    if (!position) {
      setPosition(target);
      return;
    }
    cancelFrame();
    const step = () => {
      setPosition((current) => {
        const next = current ? springStep(current, target) : target;
        if (next) frame.current = view.requestAnimationFrame(step);
        else frame.current = null;
        return next ?? target;
      });
    };
    frame.current = view.requestAnimationFrame(step);
    return cancelFrame;
  }, [target?.x, target?.y, fullscreen, libraryOpen, view]);

  useEffect(() => cancelFrame, [cancelFrame]);

  useEffect(() => {
    if (!runtime || !video || !viewport) return;
    if (fullscreen) runtime.setVideoBounds({ ...fullscreenVideoBounds(viewport), radius: 0 });
    else if (docked && dockBounds) runtime.setVideoBounds({ x: dockBounds.x, y: dockBounds.y, width, height: videoHeight });
    else if (!libraryOpen && position) runtime.setVideoBounds({ x: position.x, y: position.y, width, height: videoHeight });
  }, [runtime, libraryOpen, docked, dockBounds, video, fullscreen, position?.x, position?.y, width, videoHeight, viewport?.width, viewport?.height]);

  const [revealUntil, setRevealUntil] = useState(0);
  const reveal = useCallback(() => setRevealUntil(Date.now() + REVEAL_MS), []);
  useEffect(() => {
    if (video) reveal();
  }, [video, trackKey, reveal]);
  useEffect(() => {
    if (!revealUntil) return;
    const timer = setTimeout(() => setRevealUntil((current) => (current <= Date.now() ? 0 : current)), revealUntil - Date.now() + 20);
    return () => clearTimeout(timer);
  }, [revealUntil]);
  const revealed = docked ? !!dock?.focus : (controlling && !fullscreen) || revealUntil > Date.now();

  useEffect(() => {
    if (runtime) runtime.setVideoVisible(visible && video && (!docked || !!dockBounds?.width));
  }, [runtime, visible, video, docked, dockBounds?.width]);

  useEffect(() => {
    if (snapshot?.overlayControl && !player?.track) runtime?.stopOverlayControl();
  }, [snapshot?.overlayControl, player?.track, runtime]);

  const qamWasOpen = useRef(qamOpen);
  useEffect(() => {
    const opened = qamOpen && !qamWasOpen.current;
    qamWasOpen.current = qamOpen;
    if (opened && controlling) runtime?.stopOverlayControl();
  }, [qamOpen, controlling, runtime]);

  useEffect(() => {
    if (!fullscreen || !runtime) return;
    try {
      const trees = getGamepadNavigationTrees() as { id?: string; m_ID?: string; m_Root?: { m_element?: Element }; Root?: { Element?: Element } }[] | undefined;
      const tree = trees?.find((candidate) => (candidate.id ?? candidate.m_ID) === "MainNavMenuContainer");
      const doc = (tree?.m_Root?.m_element ?? tree?.Root?.Element)?.ownerDocument;
      if (!doc) return;
      const onVisibility = () => {
        if (doc.visibilityState === "visible") runtime.stopOverlayControl();
      };
      doc.addEventListener("visibilitychange", onVisibility);
      onVisibility();
      return () => doc.removeEventListener("visibilitychange", onVisibility);
    } catch {
      return;
    }
  }, [fullscreen, runtime]);

  const wasFullscreen = useRef(fullscreen);
  useLayoutEffect(() => {
    if (wasFullscreen.current && !fullscreen && dockElement?.parentElement) focusLibraryElement(dockElement.parentElement);
    wasFullscreen.current = fullscreen;
  }, [fullscreen, dockElement]);

  const hasTrack = !!player?.track;
  useEffect(() => {
    const doc = surface?.document;
    if (!doc || !runtime || !hasTrack || libraryOpen) return;
    return onQamLeftEdge(doc, () => runtime.startOverlayControl());
  }, [surface?.document, runtime, hasTrack, libraryOpen]);

  useEffect(() => {
    if (!controlling || fullscreen || !runtime) return;
    const timer = setTimeout(() => runtime.stopOverlayControl(), CONTROL_IDLE_MS);
    return () => clearTimeout(timer);
  }, [controlling, fullscreen, lastInput, runtime]);

  const settle = (next: OverlayCorner) => {
    if (fullscreen) return;
    setCorner(next);
    if (next !== music?.overlayCorner) void runtime?.updateSettings((s) => ({ ...s, music: { ...s.music, overlayCorner: next } }));
  };

  const cycleSize = (direction: -1 | 1 = 1, wrap = true) => {
    if (fullscreen) return;
    const current = music?.videoScale ?? 40;
    const stepped = current + direction * SCALE_STEP;
    const next = wrap && stepped > MAX_SCALE ? MIN_SCALE : Math.max(MIN_SCALE, Math.min(MAX_SCALE, stepped));
    if (next !== current) void runtime?.updateSettings((s) => ({ ...s, music: { ...s.music, videoScale: next } }));
  };

  const toggleFullscreen = () => {
    if (!video || (inGame && !canDrawOverGames())) return;
    drag.current = null;
    cancelFrame();
    reveal();
    runtime?.setVideoFullscreen(!fullscreen);
  };

  const lastButton = useRef({ button: 0, at: 0 });
  // Control mode is entered with ← on the QAM tabs; that same press must not also move the card.
  const enteredAt = useRef(0);
  useEffect(() => {
    if (controlling) enteredAt.current = Date.now();
  }, [controlling]);
  const onControlButton = (button: number) => {
    if (!runtime || !player) return;
    const now = Date.now();
    if (button === GamepadButton.LEFT && now - enteredAt.current < ENTRY_GUARD_MS) return;
    // Steam may also turn a key into its gamepad event; one press must act once.
    if (lastButton.current.button === button && now - lastButton.current.at < 80) return;
    lastButton.current = { button, at: now };
    setLastInput(Date.now());
    reveal();
    const action = controlAction(button, settled);
    if (action.kind === "toggle") (player.status === "playing" || player.status === "loading" ? runtime.pauseMusic() : runtime.resumeMusic());
    else if (action.kind === "next") runtime.nextTrack();
    else if (action.kind === "video" && runtime.canShowVideo()) runtime.toggleVideo();
    else if (action.kind === "fullscreen") toggleFullscreen();
    else if (action.kind === "move") settle(action.corner);
    else if (action.kind === "seek") runtime.seekBy(action.seconds);
    else if (action.kind === "resize") cycleSize(action.direction, false);
    else if (action.kind === "exit") {
      if (fullscreen && !action.then) runtime.setVideoFullscreen(false);
      else runtime.stopOverlayControl(action.then);
    }
  };

  useEffect(() => {
    const doc = view?.document;
    if (!controlling || !doc || libraryOpen) return;
    const onKey = (event: KeyboardEvent) => {
      const button = keyToButton(event.key);
      if (button === null) return;
      event.preventDefault();
      event.stopPropagation();
      onControlButton(button);
    };
    doc.addEventListener("keydown", onKey, true);
    return () => doc.removeEventListener("keydown", onKey, true);
  });

  const controlHandler = useRef(onControlButton);
  controlHandler.current = onControlButton;
  useEffect(() => {
    // The card never holds Steam's focus (over a game or over Home), so its buttons are taken from
    // Steam's input itself once the QAM has closed.
    if (!controlling || libraryOpen || qamOpen) return;
    return captureButtons(CONTROL_BUTTONS, (button) => controlHandler.current(button));
  }, [controlling, qamOpen, libraryOpen, fullscreen]);

  const onPointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    reveal();
    if (docked) {
      const control = (event.target as HTMLElement).closest("[data-video-control]")?.getAttribute("data-video-control") ?? "toggle";
      const target = dockElement?.querySelector<HTMLElement>(`[data-library-control="${control}"]`) ?? dockElement?.parentElement;
      if (target) focusLibraryElement(target);
      return;
    }
    if (fullscreen || !position) return;
    drag.current = { pointer: event.pointerId, start: { x: event.clientX, y: event.clientY }, grab: { x: event.clientX - position.x, y: event.clientY - position.y }, moved: false };
  };

  const onPointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (fullscreen) { reveal(); return; }
    const current = drag.current;
    if (!current || current.pointer !== event.pointerId || !viewport) return;
    if (!current.moved) {
      if (Math.hypot(event.clientX - current.start.x, event.clientY - current.start.y) < DRAG_THRESHOLD_PX) return;
      current.moved = true;
      cancelFrame();
      event.currentTarget.setPointerCapture(event.pointerId);
    }
    setPosition(clampPosition({ x: event.clientX - current.grab.x, y: event.clientY - current.grab.y }, size, viewport));
  };

  const onPointerUp = (event: ReactPointerEvent<HTMLDivElement>) => {
    const current = drag.current;
    drag.current = null;
    if (!current?.moved || !position || !viewport || !runtime) return;
    event.preventDefault();
    settle(nearestCorner(position, size, viewport, rightInset));
  };

  if (!runtime || !player?.track || !host || !viewport) return null;
  const busy = player.status === "playing" || player.status === "loading" || player.status === "retrying";
  const at = fullscreen ? { x: 0, y: 0 } : docked ? dockBounds : position ?? target;

  const isFavorite = runtime.isFavoriteTrack();
  const toggleFavorite = runtime.canFavoriteTrack() ? () => runtime.toggleFavoriteTrack() : undefined;
  const playerCard = video ? (
    <VideoCard
      height={videoHeight}
      title={player.track?.title ?? ""}
      subtitle={player.track?.subtitle ?? ""}
      busy={busy}
      revealed={revealed}
      libraryFocus={docked ? dock?.focus ?? null : undefined}
      onToggle={() => (busy ? runtime.pauseMusic() : runtime.resumeMusic())}
      onNext={!docked && !player.track?.live ? () => runtime.nextTrack() : undefined}
      onCollapse={docked ? undefined : () => runtime.toggleVideo()}
      live={!!player.track?.live}
      fraction={player.duration ? player.position / player.duration : 0}
      onSeek={(f) => runtime.seekFraction(f)}
      onResize={fullscreen || docked ? undefined : () => cycleSize()}
      fullscreen={fullscreen}
      onFullscreen={!docked && (!inGame || canDrawOverGames()) ? toggleFullscreen : undefined}
      favorite={isFavorite}
      onFavorite={docked ? undefined : toggleFavorite}
    />
  ) : (
    <NowPlaying
      compact
      touchOnly
      flush
      inGame={inGame}
      player={player}
      onToggle={() => (busy ? runtime.pauseMusic() : runtime.resumeMusic())}
      onNext={() => runtime.nextTrack()}
      onPrevious={() => runtime.previousTrack()}
      onVolume={(v) => runtime.setVolume(v)}
      onSeek={(f) => runtime.seekFraction(f)}
      favorite={isFavorite}
      onFavorite={docked ? undefined : toggleFavorite}
      videoShown={video}
      onVideo={runtime.canShowVideo() ? () => runtime.toggleVideo() : undefined}
    />
  );

  return (
    <>
      {inGame && visible && <OverGameComposition level={controlling ? UIComposition.Overlay : UIComposition.Notification} />}
      {fullscreen && createPortal(<div style={{ position: "fixed", inset: 0, background: "#000", zIndex: 2147482998, pointerEvents: "none" }} />, host)}
      {createPortal(
        <div
          ref={card}
          onPointerDown={docked ? undefined : onPointerDown}
          onPointerDownCapture={docked ? onPointerDown : undefined}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={() => (drag.current = null)}
          onClickCapture={(event) => {
            if (drag.current?.moved) event.stopPropagation();
          }}
          style={{
            display: visible ? undefined : "none",
            position: "fixed",
            zIndex: 2147483000,
            left: at?.x ?? 0,
            top: at?.y ?? 0,
            width,
            visibility: at ? "visible" : "hidden",
            touchAction: "none",
            userSelect: "none",
          }}
        >
          <div style={{ borderRadius: fullscreen ? 0 : 18, boxShadow: controlling && !fullscreen ? `0 0 0 2px rgba(${theme.color.accentRgb},0.9), 0 0 24px rgba(${theme.color.accentRgb},0.35)` : "none" }}>
            {playerCard}
          </div>
          {controlling && !libraryOpen && (!fullscreen || revealed) && (
            <div style={{ ...(fullscreen ? { position: "absolute", top: 8, left: "50%", transform: "translateX(-50%)" } as const : { marginTop: 8 }), pointerEvents: "none", padding: "6px 10px", borderRadius: 12, background: "rgba(10,12,18,0.82)", color: "rgba(255,255,255,0.86)", fontSize: 11, fontWeight: 600, textAlign: "center" }}>
              {t(fullscreen ? "ambient.overlay.fullscreenHint" : "ambient.overlay.hint")}
            </div>
          )}
        </div>,
        host,
      )}
    </>
  );
};
