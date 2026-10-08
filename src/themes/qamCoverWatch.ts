import { findQamNavigationDocument } from "../system/uiActivity";

const CHECK_DELAY_MS = 500;
const FIND_RETRY_MS = [1_000, 5_000, 15_000] as const;

// A filter on the root gives Steam's fixed Quick Access layers a new containing block and they
// render off-screen: the whole menu goes black, Panel included.
export function qamCovered(document: Document): boolean {
  const view = document.defaultView;
  if (!view) return false;
  return [document.documentElement, document.body].some(
    (element) => element !== null && !["", "none"].includes(view.getComputedStyle(element).filter),
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
      const delay = FIND_RETRY_MS[attempt++];
      if (delay !== undefined) timer = setTimeout(attach, delay);
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
