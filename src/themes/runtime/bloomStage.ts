import { safeArtworkUrl } from "./artwork";

const STAGE_ID = "pdc-obsidian-bloom-stage";
const FOCUS_X = "--pdc-obsidian-focus-x";
const FOCUS_Y = "--pdc-obsidian-focus-y";

export interface BloomStage {
  update(artwork: string, rect: DOMRect): void;
  dispose(): void;
}

const NO_BLOOM_STAGE: BloomStage = {
  update() {},
  dispose() {},
};

function restoreProperty(root: HTMLElement, name: string, previous: string): void {
  if (previous) root.style.setProperty(name, previous);
  else root.style.removeProperty(name);
}

export function startBloomStage(doc: Document): BloomStage {
  if (!doc.body || doc.getElementById(STAGE_ID)) return NO_BLOOM_STAGE;
  const root = doc.documentElement;
  const previousX = root.style.getPropertyValue(FOCUS_X);
  const previousY = root.style.getPropertyValue(FOCUS_Y);
  const host = doc.createElement("div");
  host.id = STAGE_ID;
  host.setAttribute("aria-hidden", "true");
  const layers = ["a", "b"].map((id) => {
    const layer = doc.createElement("div");
    layer.dataset.pdcBloomLayer = id;
    host.append(layer);
    return layer;
  });
  const atmosphere = doc.createElement("div");
  atmosphere.dataset.pdcBloomAtmosphere = "true";
  host.append(atmosphere);
  doc.body.prepend(host);

  let activeLayer = -1;
  let currentArtwork: string | null = null;
  let disposed = false;

  return {
    update(artwork, rect) {
      if (disposed) return;
      const safeArtwork = safeArtworkUrl(artwork);
      if (!safeArtwork) return;
      root.style.setProperty(FOCUS_X, `${Math.round(rect.left + rect.width / 2)}px`);
      root.style.setProperty(FOCUS_Y, `${Math.round(rect.top + rect.height / 2)}px`);
      if (safeArtwork === currentArtwork) return;
      const nextLayer = activeLayer === 0 ? 1 : 0;
      layers[nextLayer].style.backgroundImage = `url(${JSON.stringify(safeArtwork)})`;
      if (activeLayer >= 0) layers[activeLayer].removeAttribute("data-pdc-bloom-active");
      layers[nextLayer].dataset.pdcBloomActive = "true";
      activeLayer = nextLayer;
      currentArtwork = safeArtwork;
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      host.remove();
      restoreProperty(root, FOCUS_X, previousX);
      restoreProperty(root, FOCUS_Y, previousY);
    },
  };
}
