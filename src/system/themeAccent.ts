import { applyThemeAccent } from "./accentColor";

export const THEME_ACCENT_PROPERTY = "--pdc-theme-accent";

export function readThemeAccent(doc: Document): string | null {
  const root = doc.documentElement;
  const view = doc.defaultView;
  if (!root || !view) return null;
  return view.getComputedStyle(root).getPropertyValue(THEME_ACCENT_PROPERTY).trim() || null;
}

// CSS Loader adds, removes and rewrites <style> nodes when a theme or one of its
// options changes; re-reading on those mutations keeps "default" in step with it.
export function watchThemeAccent(doc: Document): () => void {
  const view = doc.defaultView;
  const head = doc.head;
  if (!view || !head) return () => {};
  let frame = 0;
  const sync = () => {
    frame = 0;
    applyThemeAccent(readThemeAccent(doc));
  };
  sync();
  const observer = new view.MutationObserver(() => {
    if (!frame) frame = view.requestAnimationFrame(sync);
  });
  observer.observe(head, { childList: true, subtree: true, characterData: true });
  return () => {
    observer.disconnect();
    if (frame) view.cancelAnimationFrame(frame);
  };
}
