import { useLayoutEffect, useRef, useState } from "react";

interface TrayPosition {
  left: number;
  width: number;
  bottom: number;
}

export const PANEL_INSET = 16;
const POSITION_POLL_MS = 100;

function scrollViewport(anchor: HTMLElement): HTMLElement | null {
  const qamContent = anchor.closest<HTMLElement>("[id^='quickaccess_content_']");
  if (qamContent) return qamContent;
  const view = anchor.ownerDocument.defaultView;
  for (let node = anchor.parentElement; node; node = node.parentElement) {
    const overflow = view?.getComputedStyle(node).overflowY || node.style.overflowY;
    if (overflow === "auto" || overflow === "scroll") return node;
  }
  return null;
}

function trayPosition(anchor: HTMLElement): TrayPosition {
  const view = anchor.ownerDocument.defaultView ?? window;
  const viewport = scrollViewport(anchor)?.getBoundingClientRect();
  const left = viewport?.left ?? 0;
  const width = viewport?.width ?? view.innerWidth;
  const bottom = viewport ? view.innerHeight - viewport.bottom : 0;
  return {
    left: left + PANEL_INSET,
    width: Math.max(0, width - PANEL_INSET * 2),
    bottom: Math.max(0, bottom) + PANEL_INSET,
  };
}

export function useFloatingTrayPosition() {
  const anchorRef = useRef<HTMLSpanElement>(null);
  const trayRef = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(0);
  const [position, setPosition] = useState<TrayPosition>({
    left: PANEL_INSET,
    width: Math.max(0, window.innerWidth - PANEL_INSET * 2),
    bottom: PANEL_INSET,
  });

  useLayoutEffect(() => {
    const anchor = anchorRef.current;
    if (!anchor) return;
    const view = anchor.ownerDocument.defaultView ?? window;
    const viewport = scrollViewport(anchor);
    const update = () => {
      const tray = trayRef.current;
      if (tray) setHeight(tray.getBoundingClientRect().height);
      setPosition((current) => {
        const next = trayPosition(anchor);
        return current.left === next.left
          && current.width === next.width
          && current.bottom === next.bottom
          ? current
          : next;
      });
    };
    const resize = typeof view.ResizeObserver === "function"
      ? new view.ResizeObserver(update)
      : null;
    if (resize && viewport) resize.observe(viewport);
    if (trayRef.current) resize?.observe(trayRef.current);
    view.addEventListener("resize", update);
    // QAM slides with transforms, which do not notify ResizeObserver.
    const poll = view.setInterval(update, POSITION_POLL_MS);
    update();
    return () => {
      resize?.disconnect();
      view.removeEventListener("resize", update);
      view.clearInterval(poll);
    };
  }, []);

  return { anchorRef, trayRef, position, height };
}
