import { type RefObject, useLayoutEffect } from "react";

import { createThemeNavigationAccess } from "../themes/runtime/navigationAccess";

const gamepadNavigation = createThemeNavigationAccess();
const visible = (element: HTMLElement) => element.isConnected && element.getClientRects().length > 0;
const focusFirst = (candidates: HTMLElement[]) => candidates.some((element) => visible(element) && gamepadNavigation.focus(element));
const WATCH_RETRY_MS = 50;
const WATCH_WINDOW_MS = 2000;
// Marks the control that should take focus when it replaces a removed one, such as
// Cancel in a destructive confirmation.
export const PREFERRED_FOCUS = "data-preferred-focus";

function neighbours(root: Element, block: HTMLElement): HTMLElement[] {
  const group = block.parentElement?.closest(".Focusable") ?? root;
  const candidates = Array.from(root.querySelectorAll<HTMLElement>(".Focusable"))
    .filter((element) => !block.contains(element) && !element.contains(block));
  const before = candidates.filter((element) =>
    Boolean(element.compareDocumentPosition(block) & Node.DOCUMENT_POSITION_FOLLOWING)).reverse();
  const after = candidates.filter((element) => !before.includes(element));
  const inGroup = (element: HTMLElement) => group.contains(element);
  return [...before.filter(inGroup), ...after.filter(inGroup), ...before, ...after];
}

// A focused node that unmounts leaves Steam with no focus at all, and Steam keeps
// focus on the pressed control until its activation ends, so focus cannot be moved
// beforehand. Call this when the block holding focus is about to go: once it is gone,
// focus moves to what replaced it, or, if focus was lost, to the nearest control.
export function refocusWhenRemoved(block: HTMLElement | null): void {
  if (!block?.querySelector(".gpfocus") && !block?.classList.contains("gpfocus")) return;
  const root = block.closest(".pdc-root");
  const view = block.ownerDocument.defaultView;
  if (!root || !view) return;
  const places: Element[] = [];
  for (let parent = block.parentElement; parent && root.contains(parent); parent = parent.parentElement) places.push(parent);
  const known = new Set(root.querySelectorAll(".Focusable"));
  const fallbacks = neighbours(root, block);
  const deadline = Date.now() + WATCH_WINDOW_MS;
  const watch = () => {
    if (block.isConnected) {
      if (Date.now() < deadline) view.setTimeout(watch, WATCH_RETRY_MS);
      return;
    }
    if (!root.isConnected) return;
    const fresh = (scope: Element | undefined) => scope
      ? Array.from(scope.querySelectorAll<HTMLElement>(".Focusable")).filter((element) => !known.has(element) && visible(element))
      : [];
    const preferred = fresh(root).filter((element) => element.hasAttribute(PREFERRED_FOCUS));
    if (preferred.length) {
      if (!preferred.some((element) => element.classList.contains("gpfocus"))) focusFirst(preferred);
      return;
    }
    const place = places.find((element) => element.isConnected);
    const replacements = fresh(place);
    if (replacements.length) {
      if (!place?.querySelector(".gpfocus")) focusFirst(replacements);
      return;
    }
    if (!root.querySelector(".gpfocus")) focusFirst(fallbacks);
  };
  view.setTimeout(watch, WATCH_RETRY_MS);
}

export function useRefocusWhenRemoved(ref: RefObject<HTMLElement | null>): void {
  useLayoutEffect(() => {
    const element = ref.current;
    return () => refocusWhenRemoved(element);
  }, [ref]);
}
