// Publishes the QAM panel's own document. Our content, the plugin list and the
// panel chrome all render into it; the plugin's `document` global is a different
// one (see FocusRoot). Consumers that must reach the surrounding panel read it here.

type Listener = (doc: Document) => void;

let current: Document | null = null;
const listeners = new Set<Listener>();

export function setQamDocument(doc: Document): void {
  if (doc === current) return;
  current = doc;
  for (const l of listeners) {
    try {
      l(doc);
    } catch {
      /* a listener must never break the mount */
    }
  }
}

export function onQamDocument(cb: Listener): () => void {
  listeners.add(cb);
  if (current) {
    try {
      cb(current);
    } catch {
      /* best-effort */
    }
  }
  return () => {
    listeners.delete(cb);
  };
}
