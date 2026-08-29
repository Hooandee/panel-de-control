import { LOCAL_THEME_CATALOG } from "../catalog";
import { CssLoaderAdapter } from "../cssLoaderAdapter";
import { createDeckyCssLoaderHost } from "../deckyCssLoaderHost";
import { createObsidianBloomRuntime } from "./obsidianBloom";
import { ThemeRuntimeManager } from "./runtimeManager";
import { startThemeRuntimeWatcher } from "./runtimeWatcher";

interface RuntimeManagerLike {
  reconcile(snapshot: import("../cssLoaderTypes").CssLoaderSnapshot): void;
  dispose(): void;
}

export interface SteamRuntimeBridge {
  reconcile(snapshot: import("../cssLoaderTypes").CssLoaderSnapshot): void;
  dispose(): void;
}

export function createSteamRuntimeBridge(
  getSteamDocument: () => Document | null,
  createManager: (doc: Document) => RuntimeManagerLike = (doc) => new ThemeRuntimeManager({
    modules: [createObsidianBloomRuntime(doc)],
  }),
): SteamRuntimeBridge {
  let currentDocument: Document | null = null;
  let manager: RuntimeManagerLike | null = null;

  const release = () => {
    manager?.dispose();
    manager = null;
    currentDocument = null;
  };

  return {
    reconcile(snapshot) {
      let nextDocument: Document | null = null;
      try {
        nextDocument = getSteamDocument();
      } catch {
        release();
        return;
      }
      if (nextDocument !== currentDocument) {
        release();
        currentDocument = nextDocument;
        if (nextDocument) {
          try {
            manager = createManager(nextDocument);
          } catch {
            currentDocument = null;
            manager = null;
          }
        }
      }
      manager?.reconcile(snapshot);
    },
    dispose: release,
  };
}

interface ThemesRuntimeOptions {
  deckyHost: unknown;
  getSteamDocument(): Document | null;
  signalTarget?: Pick<EventTarget, "addEventListener" | "removeEventListener">;
}

export function startThemesRuntime({
  deckyHost,
  getSteamDocument,
  signalTarget,
}: ThemesRuntimeOptions): () => void {
  const minimumBackendVersion = Math.max(...LOCAL_THEME_CATALOG.themes
    .map((theme) => theme.minimumCssLoaderBackendVersion));
  const adapter = new CssLoaderAdapter(createDeckyCssLoaderHost(deckyHost), { minimumBackendVersion });
  const bridge = createSteamRuntimeBridge(getSteamDocument);
  const watcher = startThemeRuntimeWatcher({
    inspect: () => adapter.inspect(),
    reconcile: (snapshot) => bridge.reconcile(snapshot),
    eventTarget: signalTarget,
  });

  return () => {
    watcher.dispose();
    bridge.dispose();
  };
}
