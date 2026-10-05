import { showModal as showDeckyModal } from "@decky/ui";

import { getQamDocument } from "../qamDocument";
import { createThemeNavigationAccess } from "../themes/runtime/navigationAccess";

const gamepadNavigation = createThemeNavigationAccess();
const REMOUNT_FRAMES = 60;
let openModals = 0;

function controlLabel(element: Element): string {
  return (element.getAttribute("aria-label") || element.textContent || "").trim();
}

// Steam closes the QAM under a modal and reopens it afterwards, which remounts the
// panel: the opener is usually a fresh node by then, found again by its label.
function findOpener(doc: Document, opener: HTMLElement, label: string): HTMLElement | null {
  if (opener.isConnected) return opener;
  if (!label) return null;
  return Array.from(doc.querySelectorAll<HTMLElement>(".pdc-root .Focusable"))
    .find((element) => controlLabel(element) === label) ?? null;
}

function returnFocus(doc: Document, opener: HTMLElement, label: string): void {
  const view = doc.defaultView;
  if (!view) return;
  let frames = 0;
  const attempt = () => {
    const target = findOpener(getQamDocument() ?? doc, opener, label);
    if (target) {
      gamepadNavigation.focus(target);
      return;
    }
    if (++frames < REMOUNT_FRAMES) view.requestAnimationFrame(attempt);
  };
  view.requestAnimationFrame(attempt);
}

// Steam drops gamepad focus to the QAM tab strip when a modal closes; hand it back
// to the panel control that opened it. Nested modals open from another document,
// so only the outermost one has a panel control to return to.
export const showModal: typeof showDeckyModal = (modal, parent, props) => {
  const doc = openModals === 0 ? getQamDocument() : null;
  const opener = doc?.querySelector<HTMLElement>(".pdc-root .gpfocus") ?? null;
  const label = opener ? controlLabel(opener) : "";
  openModals += 1;
  let closed = false;
  const onClose = () => {
    if (closed) return;
    closed = true;
    openModals -= 1;
    props?.fnOnClose?.();
    if (doc && opener) returnFocus(doc, opener, label);
  };
  try {
    const result = showDeckyModal(modal, parent, { ...props, fnOnClose: onClose });
    return {
      ...result,
      Close: () => {
        result.Close();
        onClose();
      },
    };
  } catch (error) {
    if (!closed) openModals -= 1;
    throw error;
  }
};
