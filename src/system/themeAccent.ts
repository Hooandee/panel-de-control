import { applyThemeAccent } from "./accentColor";
import { applyThemeTokens, readThemeTokens } from "./themeTokens";

export const THEME_ACCENT_PROPERTY = "--pdc-theme-accent";

export function readThemeAccent(doc: Document): string | null {
  const root = doc.documentElement;
  const view = doc.defaultView;
  if (!root || !view) return null;
  return view.getComputedStyle(root).getPropertyValue(THEME_ACCENT_PROPERTY).trim() || null;
}

interface Watch {
  stale: boolean;
  mounted: number;
  frame: number;
  observers: MutationObserver[];
}

// Decky mounts the panel again on every quick access menu opening, in the same QAM document. Reading the
// computed tokens forces a style pass over that whole menu while Steam is still building it (~21 ms on the
// Deck LCD, every opening). The document keeps one watcher: the values are read again only after CSS Loader
// rewrote a style, the root's style or class changed or the window resized, and only while the panel is up.
const watches = new WeakMap<Document, Watch>();

// CSS Loader adds, removes and rewrites <style> nodes when a theme or one of its
// options changes; re-reading on those mutations keeps "default" in step with it.
export function watchThemeAccent(doc: Document): () => void {
  const view = doc.defaultView;
  const head = doc.head;
  if (!view || !head) return () => {};
  let watch = watches.get(doc);
  if (!watch) {
    const created: Watch = { stale: true, mounted: 0, frame: 0, observers: [] };
    watch = created;
    watches.set(doc, created);
    const schedule = () => {
      created.stale = true;
      if (created.mounted && !created.frame) created.frame = view.requestAnimationFrame(() => sync(created));
    };
    const styles = new view.MutationObserver(schedule);
    styles.observe(head, { childList: true, subtree: true, characterData: true });
    const root = new view.MutationObserver(schedule);
    root.observe(doc.documentElement, { attributes: true, attributeFilter: ["style", "class"] });
    created.observers.push(styles, root);
    view.addEventListener("resize", schedule);
  }
  const sync = (target: Watch) => {
    target.frame = 0;
    target.stale = false;
    applyThemeAccent(readThemeAccent(doc));
    applyThemeTokens(readThemeTokens(doc));
  };
  const current = watch;
  current.mounted += 1;
  // A change made in this same task has not reached the observers' callbacks yet.
  for (const observer of current.observers) if (observer.takeRecords().length) current.stale = true;
  if (current.stale) sync(current);
  return () => {
    current.mounted = Math.max(0, current.mounted - 1);
    if (!current.mounted && current.frame) {
      view.cancelAnimationFrame(current.frame);
      current.frame = 0;
    }
  };
}
