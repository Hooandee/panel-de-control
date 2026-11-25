import { onQamDocument } from "../qamDocument";
import { findQamNavigationDocument } from "../system/uiActivity";

export interface QamSurface {
  document: Document;
  visible: boolean;
}

const DISCOVER_MS = 2000;

/**
 * The QAM window's document and whether it is showing, without Panel being opened: found through
 * the gamepad navigation trees, and replaced whenever Panel publishes a newer one.
 */
export function subscribeQamSurface(
  listener: (surface: QamSurface | null) => void,
  discover: () => Document | null = findQamNavigationDocument,
): () => void {
  let doc: Document | null = null;
  let stopped = false;
  const emit = () => {
    if (!stopped) listener(doc ? { document: doc, visible: doc.visibilityState === "visible" } : null);
  };
  const attach = (next: Document | null) => {
    if (!next || next === doc) return;
    doc?.removeEventListener("visibilitychange", emit);
    doc = next;
    doc.addEventListener("visibilitychange", emit);
    emit();
  };
  attach(discover());
  const unsubscribe = onQamDocument(attach);
  const poll = setInterval(() => attach(discover()), DISCOVER_MS);
  return () => {
    stopped = true;
    clearInterval(poll);
    unsubscribe();
    doc?.removeEventListener("visibilitychange", emit);
  };
}

/**
 * Width the QAM panel takes on screen. Its window starts at the panel's edge and runs past the
 * right of the screen, so the panel is the tall, narrow block at the start of its document.
 * Window positions are not reliable under gamescope, so this is measured from the layout.
 */
export function qamPanelWidth(doc: Document): number | null {
  const view = doc.defaultView;
  if (!view) return null;
  let right = 0;
  for (const element of Array.from(doc.querySelectorAll("div"))) {
    const rect = element.getBoundingClientRect();
    if (rect.height >= view.innerHeight * 0.8 && rect.width > 150 && rect.width < view.innerWidth * 0.7 && rect.left < 80) {
      right = Math.max(right, rect.right);
    }
  }
  return right > 0 ? right : null;
}

const TAB_COLUMN_MAX_LEFT_PX = 40;
const TAB_COLUMN_MAX_WIDTH_PX = 90;
const DPAD_LEFT = 11;

/**
 * Calls `handler` when the player presses left while already on the QAM's tab column, the one
 * spot where left has no meaning of its own. Steam delivers gamepad input to the focused QAM
 * node as `vgp_onbuttondown` DOM events.
 */
export function onQamLeftEdge(doc: Document, handler: () => void): () => void {
  const onTabColumn = (target: EventTarget | null) => {
    const element = target as Element | null;
    if (!element?.getBoundingClientRect) return false;
    const rect = element.getBoundingClientRect();
    return rect.left <= TAB_COLUMN_MAX_LEFT_PX && rect.width <= TAB_COLUMN_MAX_WIDTH_PX;
  };
  const gamepad = (event: Event) => {
    if ((event as CustomEvent<{ button?: number }>).detail?.button !== DPAD_LEFT || !onTabColumn(event.target)) return;
    event.stopPropagation();
    handler();
  };
  const keyboard = (event: KeyboardEvent) => {
    if (event.key !== "ArrowLeft" || !onTabColumn(event.target ?? doc.activeElement)) return;
    event.stopPropagation();
    handler();
  };
  doc.addEventListener("vgp_onbuttondown", gamepad, true);
  doc.addEventListener("keydown", keyboard, true);
  return () => {
    doc.removeEventListener("vgp_onbuttondown", gamepad, true);
    doc.removeEventListener("keydown", keyboard, true);
  };
}
