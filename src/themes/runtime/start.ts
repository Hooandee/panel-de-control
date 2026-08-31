import type { CssLoaderSnapshot } from "../cssLoaderTypes";
import { createThemeExtensionClient } from "../themeExtensionClient";
import { ThemeExtensionRuntimeHost } from "./extensionHost";

interface RuntimeManagerLike {
  reconcile(snapshot: CssLoaderSnapshot): void;
  refreshDescriptors?(): Promise<void>;
  dispose(): void;
}

export interface SteamRuntimeBridge {
  reconcile(snapshot: CssLoaderSnapshot): void;
  dispose(): void;
}

function nodeTouchesCssLoaderStyle(node: Node): boolean {
  if (node.nodeType === node.ELEMENT_NODE) {
    const element = node as Element;
    return element.matches?.("style.css-loader-style")
      || Boolean(element.querySelector?.("style.css-loader-style"));
  }
  return Boolean(node.parentElement?.closest("style.css-loader-style"));
}

function watchCssLoaderStyles(doc: Document, onChange: () => void): () => void {
  const Observer = doc.defaultView?.MutationObserver;
  if (!Observer || !doc.head) return () => {};
  let stopped = false;
  const observer = new Observer((records) => {
    if (
      stopped
      || !records.some((record) => (
        nodeTouchesCssLoaderStyle(record.target)
        || [...record.addedNodes].some(nodeTouchesCssLoaderStyle)
        || [...record.removedNodes].some(nodeTouchesCssLoaderStyle)
      ))
    ) return;
    onChange();
  });
  try {
    observer.observe(doc.head, {
      attributes: true,
      attributeFilter: ["class", "disabled"],
      characterData: true,
      childList: true,
      subtree: true,
    });
  } catch {
    observer.disconnect();
    return () => {};
  }
  return () => {
    stopped = true;
    observer.disconnect();
  };
}

function extensionInventoryFingerprint(snapshot: CssLoaderSnapshot): string {
  if (snapshot.status !== "ready") return snapshot.status;
  return JSON.stringify(snapshot.themes
    .map((theme) => [theme.name, theme.version] as const)
    .sort(([left], [right]) => left.localeCompare(right, "en")));
}

export function createSteamRuntimeBridge(
  getSteamDocument: () => Document | null,
  createManager: (doc: Document) => RuntimeManagerLike = (doc) => new ThemeExtensionRuntimeHost({
    client: createThemeExtensionClient(),
    doc,
  }),
  onCssLoaderStylesChanged?: () => void,
): SteamRuntimeBridge {
  let currentDocument: Document | null = null;
  let manager: RuntimeManagerLike | null = null;
  let stopStyleWatch: (() => void) | null = null;
  let inventoryFingerprint: string | null = null;

  const release = () => {
    stopStyleWatch?.();
    stopStyleWatch = null;
    manager?.dispose();
    manager = null;
    currentDocument = null;
    inventoryFingerprint = null;
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
            if (onCssLoaderStylesChanged) {
              stopStyleWatch = watchCssLoaderStyles(nextDocument, onCssLoaderStylesChanged);
            }
          } catch {
            currentDocument = null;
            manager = null;
          }
        }
      }
      const nextInventoryFingerprint = extensionInventoryFingerprint(snapshot);
      const inventoryChanged = inventoryFingerprint !== null
        && inventoryFingerprint !== nextInventoryFingerprint;
      inventoryFingerprint = nextInventoryFingerprint;
      manager?.reconcile(snapshot);
      if (inventoryChanged) void manager?.refreshDescriptors?.();
    },
    dispose: release,
  };
}

interface ThemesRuntimeClient {
  getSnapshot(): { snapshot: CssLoaderSnapshot };
  subscribe(listener: () => void, refreshIntervalMs?: number): () => void;
  refresh(): Promise<void>;
}

interface ThemesRuntimeOptions {
  client: ThemesRuntimeClient;
  getSteamDocument(): Document | null;
  createManager?(doc: Document): RuntimeManagerLike;
}

export function startThemesRuntime({
  client,
  getSteamDocument,
  createManager,
}: ThemesRuntimeOptions): () => void {
  const bridge = createSteamRuntimeBridge(
    getSteamDocument,
    createManager,
    () => { void client.refresh(); },
  );
  const reconcile = () => bridge.reconcile(client.getSnapshot().snapshot);
  const unsubscribe = client.subscribe(reconcile, 30_000);
  let stopped = false;
  reconcile();

  return () => {
    if (stopped) return;
    stopped = true;
    unsubscribe();
    bridge.dispose();
  };
}
