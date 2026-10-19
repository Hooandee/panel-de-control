import { type CSSProperties, type RefObject, useLayoutEffect } from "react";

export const STICKY_TRAY_INSET = 16;

// A fixed tray inside the transformed QAM blanks the panel, so trays stick to the end of the scroll content.
export const stickyTrayStyle: CSSProperties = {
  position: "sticky",
  bottom: STICKY_TRAY_INSET,
  zIndex: 1,
  marginTop: STICKY_TRAY_INSET,
  boxSizing: "border-box",
};

function scrollContainer(node: HTMLElement): HTMLElement | null {
  const view = node.ownerDocument.defaultView;
  for (let parent = node.parentElement; parent; parent = parent.parentElement) {
    const overflow = view?.getComputedStyle(parent).overflowY;
    if (overflow === "auto" || overflow === "scroll") return parent;
  }
  return null;
}

// Steam scrolls gamepad focus into view without knowing the tray covers the bottom edge.
export function useStickyTray(trayRef: RefObject<HTMLElement | null>): void {
  useLayoutEffect(() => {
    const tray = trayRef.current;
    const container = tray && scrollContainer(tray);
    if (!tray || !container) return;
    const previous = container.style.scrollPaddingBottom;
    const reserve = () => {
      container.style.scrollPaddingBottom = `${tray.getBoundingClientRect().height + STICKY_TRAY_INSET * 2}px`;
    };
    const view = tray.ownerDocument.defaultView;
    // Steam only scrolls when focus moves, so a tray appearing under the focused control would hide it.
    const revealFocus = () => {
      const focused = container.querySelector<HTMLElement>(".gpfocus");
      if (!focused || tray.contains(focused) || tray.getClientRects().length === 0) return;
      const covered = focused.getBoundingClientRect().bottom - tray.getBoundingClientRect().top + STICKY_TRAY_INSET;
      if (covered > STICKY_TRAY_INSET) container.scrollTop += covered;
    };
    const resize = view && typeof view.ResizeObserver === "function" ? new view.ResizeObserver(reserve) : null;
    resize?.observe(tray);
    reserve();
    revealFocus();
    return () => {
      resize?.disconnect();
      container.style.scrollPaddingBottom = previous;
    };
  }, [trayRef]);
}
