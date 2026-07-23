import { translate } from "./i18n";
import { onQamDocument } from "./qamDocument";
import { PLUGIN_IDENTITY_NAME, nextRowText } from "./pluginListName";

// The shared document mutates constantly, so a scan runs at most once per window;
// the resulting sub-second relabel latency is imperceptible.
const SCAN_THROTTLE_MS = 400;

// Relabels our row in Decky's plugin list to the localized name. Decky has no
// display-name API, so this patches the rendered text node in the QAM document,
// leaving the identity `name` (the key for open/hide/updates) untouched.
export function startPluginListLocalizer(): () => void {
  let observer: MutationObserver | null = null;
  let attached: Document | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const scan = (doc: Document): void => {
    if (!doc.body) return;
    // Same localized string the in-panel header uses, read live so a language
    // change is picked up on the next re-render without a separate subscription.
    const target = translate("app.title");
    if (target === PLUGIN_IDENTITY_NAME) return; // default language: nothing to do
    const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node) {
      const next = nextRowText(node.nodeValue ?? "", PLUGIN_IDENTITY_NAME, target);
      if (next !== null) {
        node.nodeValue = next;
        return;
      }
      node = walker.nextNode();
    }
  };

  // Only wake when the identity string appears in a batch — the observed body is the
  // shared SteamUI document, so most mutations are unrelated (clock, downloads).
  const hasIdentityText = (node: Node): boolean => {
    if (node.nodeType === 3 /* TEXT_NODE */) {
      return node.nodeValue === PLUGIN_IDENTITY_NAME;
    }
    const el = node as Element;
    if (!el.textContent?.includes(PLUGIN_IDENTITY_NAME)) return false;
    const doc = el.ownerDocument;
    if (!doc) return false;
    const walker = doc.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let n = walker.nextNode();
    while (n) {
      if (n.nodeValue === PLUGIN_IDENTITY_NAME) return true;
      n = walker.nextNode();
    }
    return false;
  };

  const relevant = (records: MutationRecord[]): boolean => {
    for (const r of records) {
      if (r.type === "characterData") {
        if (r.target.nodeValue === PLUGIN_IDENTITY_NAME) return true;
      } else {
        for (let i = 0; i < r.addedNodes.length; i++) {
          if (hasIdentityText(r.addedNodes[i])) return true;
        }
      }
    }
    return false;
  };

  const schedule = (doc: Document): void => {
    if (timer) return;
    timer = setTimeout(() => {
      timer = null;
      try {
        scan(doc);
      } catch {
        /* best-effort */
      }
    }, SCAN_THROTTLE_MS);
  };

  const attach = (doc: Document): void => {
    if (attached === doc) return;
    try {
      observer?.disconnect();
      attached = doc;
      const Obs = doc.defaultView?.MutationObserver ?? MutationObserver;
      observer = new Obs((records) => {
        if (relevant(records)) schedule(doc);
      });
      observer.observe(doc.body, {
        childList: true,
        subtree: true,
        characterData: true,
      });
      schedule(doc); // patch whatever is already rendered
    } catch {
      /* best-effort */
    }
  };

  const off = onQamDocument(attach);

  return () => {
    off();
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    try {
      observer?.disconnect();
    } catch {
      /* best-effort */
    }
    observer = null;
    attached = null;
  };
}
