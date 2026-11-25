type Surface = { doc: Document; surface: "main" | "qam" };
type Operation = "installing" | "activating" | "deactivating";
type RecordEvent = (area: string, action: string, detail: string, ok: boolean) => Promise<unknown>;
type Begin = (operation: Operation, theme?: string) => (ok: boolean) => void;
type Mark = (phase: string, fields?: Record<string, unknown>, ok?: boolean) => void;

let begin: Begin | undefined;

export function beginThemeObservation(operation: Operation, theme?: string) {
  return begin?.(operation, theme);
}

const CSS_LOADER_STYLE = "style.css-loader-style";

// Whether CSS Loader had injected anything when the user pressed again tells a theme that never
// painted apart from one that painted and was then switched off.
function cssLoaderStyles(doc: Document): number | null {
  try {
    return doc.querySelectorAll(CSS_LOADER_STYLE).length;
  } catch {
    return null;
  }
}

type SubscribeQam = (handler: (doc: Document) => void) => () => void;

function watchDocuments(docs: Surface[], mark: Mark, subscribeQam?: SubscribeQam): () => void {
  const watched = new Map<Surface["surface"], { doc: Document; release: () => void }>();
  let unsubscribe: (() => void) | undefined;
  let inputSeen = false;
  const rendered = new Set<Surface["surface"]>();
  const stop = () => {
    clearTimeout(timer);
    unsubscribe?.();
    for (const { release } of watched.values()) release();
    watched.clear();
  };
  const timer = setTimeout(() => {
    mark("expired", { inputSeen });
    stop();
  }, 120_000);
  const attach = ({ doc, surface }: Surface) => {
    const previous = watched.get(surface);
    if (previous?.doc === doc) return;
    previous?.release();
    watched.delete(surface);
    if ([...watched.values()].some((entry) => entry.doc === doc)) return;
    const view = doc.defaultView;
    if (!view) return;
    const releases: Array<() => void> = [];
    watched.set(surface, { doc, release: () => {
      for (const release of releases.splice(0)) {
        try { release(); } catch {}
      }
    } });
    // Steam can destroy either window as the menu closes.
    try {
      const frame = view.requestAnimationFrame(() => {
        if (rendered.has(surface)) return;
        rendered.add(surface);
        mark("frame", { surface, styles: cssLoaderStyles(doc) });
      });
      releases.push(() => view.cancelAnimationFrame(frame));
      const input = (event: Event) => {
        if (inputSeen || (!event.isTrusted && event.type !== "vgp_onbuttondown")) return;
        inputSeen = true;
        mark("input", { surface, type: event.type, styles: cssLoaderStyles(doc) });
        try {
          const focus = doc.activeElement;
          const next = view.requestAnimationFrame(() => {
            try {
              mark("input_frame", { surface, focusChanged: doc.activeElement !== focus });
            } catch { mark("observation_unavailable", { surface }); }
            finally { stop(); }
          });
          releases.push(() => view.cancelAnimationFrame(next));
        } catch { /* The expiry still records that input was delivered. */ }
      };
      for (const type of ["vgp_onbuttondown", "keydown", "pointerdown"]) {
        doc.addEventListener(type, input, { capture: true, passive: true });
        releases.push(() => doc.removeEventListener(type, input, true));
      }
    } catch { mark("observation_unavailable", { surface }); }
  };
  try {
    docs.forEach(attach);
    unsubscribe = subscribeQam?.((doc) => attach({ doc, surface: "qam" }));
    if (!watched.size) mark("observation_unavailable");
  } catch { mark("observation_unavailable"); }
  return stop;
}

export function configureThemeInteractionJournal(
  getDocuments: () => Surface[], record: RecordEvent, subscribeQam?: SubscribeQam,
): () => void {
  let sequence = 0;
  let cancel: (() => void) | undefined;
  const start: Begin = (operation, theme) => {
    cancel?.();
    const attempt = ++sequence;
    const started = performance.now();
    const mark: Mark = (phase, fields = {}, ok = true) => {
      try {
        const elapsedMs = Math.round(performance.now() - started);
        const detail = JSON.stringify({ attempt, operation, ...(theme ? { theme } : {}), phase, elapsedMs, ...fields });
        void record("themes", "theme_interaction", detail, ok).catch(() => undefined);
      } catch {}
    };
    let startStyles: number | null = null;
    try {
      const main = getDocuments().find((entry) => entry.surface === "main");
      if (main) startStyles = cssLoaderStyles(main.doc);
    } catch {}
    mark("started", startStyles === null ? {} : { styles: startStyles });
    return (ok) => {
      if (attempt !== sequence) return;
      if (!ok) {
        mark("failed", {}, false);
        return;
      }
      mark("completed");
      try {
        const docs = getDocuments();
        cancel = watchDocuments(docs, mark, subscribeQam);
      } catch { mark("observation_unavailable"); }
    };
  };
  begin = start;
  return () => {
    sequence++;
    cancel?.();
    if (begin === start) begin = undefined;
  };
}
