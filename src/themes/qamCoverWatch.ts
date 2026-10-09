import { findQamNavigationDocument } from "../system/uiActivity";

const CHECK_DELAY_MS = 500;
const FIND_RETRY_MS = [1_000, 5_000, 15_000] as const;
const FIND_SLOW_RETRY_MS = 60_000;

// A filter on the root gives Steam's fixed Quick Access layers a new containing block and they
// render off-screen: the whole menu goes black, Panel included. Only blamed on a theme when a
// CSS Loader style carries a filter.
export function qamCovered(document: Document): boolean {
  const view = document.defaultView;
  if (!view) return false;
  const filtered = [document.documentElement, document.body].some(
    (element) => element !== null && !["", "none"].includes(view.getComputedStyle(element).filter),
  );
  return filtered && [...document.querySelectorAll("style.css-loader-style")].some(
    (style) => /\bfilter\s*:/.test(style.textContent ?? ""),
  );
}

export function watchQamCover(
  onCovered: () => void,
  findDocument: () => Document | null = findQamNavigationDocument,
): () => void {
  let stopped = false;
  let covered = false;
  let attempt = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let observer: MutationObserver | null = null;

  const check = (document: Document) => {
    const now = qamCovered(document);
    if (now && !covered) onCovered();
    covered = now;
  };
  const attach = () => {
    if (stopped) return;
    const document = findDocument();
    const Observer = document?.defaultView?.MutationObserver;
    if (!document?.head || !Observer) {
      timer = setTimeout(attach, FIND_RETRY_MS[attempt++] ?? FIND_SLOW_RETRY_MS);
      return;
    }
    check(document);
    observer = new Observer(() => {
      clearTimeout(timer);
      timer = setTimeout(() => check(document), CHECK_DELAY_MS);
    });
    observer.observe(document.head, { childList: true, subtree: true, characterData: true });
  };

  attach();
  return () => {
    stopped = true;
    clearTimeout(timer);
    observer?.disconnect();
  };
}
