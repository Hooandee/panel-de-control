import type { ThemeRuntimeModule } from "./runtimeManager";
import type { ThemeRuntimeSurface } from "../types";
import { startSteamSurfaceSession } from "./surfaceSession";
import { safeArtworkUrl } from "./artwork";
import { startBloomStage, type BloomStage } from "./bloomStage";
import { startConstellationFocus, type ConstellationFocus } from "./constellationFocus";
import { obsidianConfigFromTheme } from "./obsidianConfig";
import { startPortalTransition, type PortalTransition } from "./portalTransition";
import { startSettingsComet } from "./settingsComet";
import { startEngineGovernor, type EngineBudget } from "./engineGovernor";
import { startOrbitalAbyss, type OrbitalAbyss } from "./orbitalAbyss";
import { ORBITAL_ABYSS_CSS } from "./orbitalAbyssCss";
import { startHorizonDossier, type HorizonDossier } from "./horizonDossier";
import { HORIZON_DOSSIER_CSS } from "./horizonDossierCss";

export { safeArtworkUrl } from "./artwork";

const STYLE_ID = "pdc-obsidian-runtime-style";
const ORBIT_RESTORE_TIMEOUT_MS = 800;
const ORBIT_SETTLE_MAX_FRAMES = 12;
const GAME_CARD_SELECTOR = [
  '#Main [role="listitem"][data-id]:not([data-id="GoToLibrary"])',
  '#Main [role="grid"] [role="gridcell"]',
].join(",");
const GAME_LINK_SELECTOR = '#Main [role="grid"] [role="link"]';

const RUNTIME_CSS = `
html[data-pdc-theme-runtime="obsidian-bloom"] {
  --pdc-obsidian-cyan: #42f5ff;
  --pdc-obsidian-magenta: #ff2fb1;
  --pdc-obsidian-ease: cubic-bezier(.18,.82,.2,1);
  --pdc-obsidian-focus-lift: -10px;
  --pdc-obsidian-focus-scale: 1.055;
  --pdc-obsidian-backdrop-opacity: .82;
  isolation: isolate;
}
html[data-pdc-theme-runtime="obsidian-bloom"] body,
html[data-pdc-theme-runtime="obsidian-bloom"] #GamepadUI_Full_Root {
  background-color: transparent !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"] #GamepadUI_Full_Root {
  position: relative;
  z-index: 1;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-motion-intensity="reduced"] {
  --pdc-obsidian-focus-lift: -4px;
  --pdc-obsidian-focus-scale: 1.02;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-motion-intensity="full"] {
  --pdc-obsidian-focus-lift: -16px;
  --pdc-obsidian-focus-scale: 1.08;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-adaptive-backdrop="subtle"] {
  --pdc-obsidian-backdrop-opacity: .48;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-adaptive-backdrop="immersive"] {
  --pdc-obsidian-backdrop-opacity: 1;
}
#pdc-obsidian-bloom-stage {
  inset: 0;
  overflow: hidden;
  pointer-events: none;
  position: fixed;
  z-index: 0;
}
#pdc-obsidian-bloom-stage [data-pdc-bloom-layer] {
  background-position: center;
  background-size: cover;
  filter: saturate(1.28) brightness(.42);
  inset: -3%;
  opacity: 0;
  position: absolute;
  transform: scale(1.045);
  transition: opacity 520ms var(--pdc-obsidian-ease), transform 900ms var(--pdc-obsidian-ease);
}
#pdc-obsidian-bloom-stage [data-pdc-bloom-active="true"] {
  opacity: var(--pdc-obsidian-backdrop-opacity);
  transform: scale(1);
}
#pdc-obsidian-bloom-stage [data-pdc-bloom-atmosphere] {
  background:
    radial-gradient(circle at var(--pdc-obsidian-focus-x, 82%) var(--pdc-obsidian-focus-y, 14%), rgba(66,245,255,.3), transparent 24%),
    radial-gradient(circle at 18% 78%, rgba(255,47,177,.24), transparent 36%),
    linear-gradient(180deg, rgba(0,0,0,.18), rgba(0,0,0,.82));
  inset: 0;
  position: absolute;
}
html[data-pdc-theme-runtime="obsidian-bloom"]:is([data-pdc-engine-budget="efficient"],[data-pdc-engine-budget="suspended"]) #pdc-obsidian-bloom-stage {
  opacity: 0;
}
#pdc-obsidian-portal {
  background: transparent;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
  position: fixed;
  transition: opacity var(--pdc-portal-reveal-duration,260ms) ease-out;
  will-change: opacity;
  z-index: 10000;
}
#pdc-obsidian-portal::before {
  background-image: var(--pdc-portal-artwork);
  background-position: center;
  background-size: cover;
  content: "";
  inset: 0;
  opacity: .16;
  position: absolute;
  transform: scale(1.04);
  z-index: 1;
}
#pdc-obsidian-portal::after {
  background:
    radial-gradient(circle at var(--pdc-portal-x) var(--pdc-portal-y), rgba(66,245,255,.22), transparent 34%),
    linear-gradient(118deg,rgba(1,3,8,.98),rgba(5,14,25,.97) 64%,rgba(12,3,15,.98));
  content: "";
  inset: 0;
  position: absolute;
  z-index: 0;
}
#pdc-obsidian-portal [data-pdc-portal-artwork] {
  background-image: var(--pdc-portal-artwork);
  background-position: center;
  background-size: cover;
  border: 1px solid rgba(255,255,255,.52);
  border-radius: 18px;
  box-shadow: 0 0 0 2px rgba(66,245,255,.46), -18px 0 52px rgba(255,47,177,.22), 18px 0 52px rgba(66,245,255,.26), 0 24px 70px rgba(0,0,0,.72);
  height: var(--pdc-portal-height);
  left: var(--pdc-portal-x);
  position: fixed;
  top: var(--pdc-portal-y);
  transform: translate3d(-50%,-50%,0);
  transform-origin: center;
  width: var(--pdc-portal-width);
  z-index: 2;
}
#pdc-obsidian-portal[data-pdc-portal-direction="entry"]::after {
  animation: pdc-obsidian-portal-entry-veil 520ms var(--pdc-obsidian-ease) both;
}
#pdc-obsidian-portal[data-pdc-portal-direction="entry"]::before {
  animation: pdc-obsidian-portal-entry-echo 700ms var(--pdc-obsidian-ease) both;
}
#pdc-obsidian-portal[data-pdc-portal-direction="entry"] [data-pdc-portal-artwork] {
  animation: pdc-obsidian-portal-entry-artwork 420ms var(--pdc-obsidian-ease) both;
}
#pdc-obsidian-portal[data-pdc-portal-direction="exit"]::after {
  animation: pdc-obsidian-portal-exit-veil 320ms var(--pdc-obsidian-ease) both;
}
#pdc-obsidian-portal[data-pdc-portal-direction="exit"]::before {
  animation: pdc-obsidian-portal-exit-echo 640ms var(--pdc-obsidian-ease) both;
}
#pdc-obsidian-portal[data-pdc-portal-direction="exit"][data-pdc-portal-exit-state="returning"]::after {
  animation: pdc-obsidian-portal-return-veil var(--pdc-portal-exit-duration) ease-out both;
}
#pdc-obsidian-portal[data-pdc-portal-direction="exit"][data-pdc-portal-exit-state="returning"]::before {
  animation: pdc-obsidian-portal-return-echo var(--pdc-portal-exit-duration) ease-out both;
}
#pdc-obsidian-portal[data-pdc-portal-direction="exit"][data-pdc-portal-exit-state="returning"] [data-pdc-portal-artwork] {
  animation: pdc-obsidian-portal-return-artwork var(--pdc-portal-exit-duration) var(--pdc-obsidian-ease) both;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-portal-phase="exit"] [data-pdc-orbit-selected="true"] {
  opacity: 0 !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-performance="off"][data-pdc-grid-motion="on"]:is([data-pdc-engine-budget="balanced"],[data-pdc-engine-budget="cinematic"]) [data-pdc-obsidian-focus="true"] {
  filter: saturate(1.12) brightness(1.07);
  transform: translate3d(0,var(--pdc-obsidian-focus-lift),0) scale(var(--pdc-obsidian-focus-scale)) !important;
  transition: transform 280ms var(--pdc-obsidian-ease), filter 220ms ease !important;
  z-index: 12 !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-performance="off"][data-pdc-grid-motion="on"]:is([data-pdc-engine-budget="balanced"],[data-pdc-engine-budget="cinematic"]) [data-pdc-obsidian-focus="true"]::after {
  border: 1px solid color-mix(in srgb, var(--pdc-obsidian-cyan) 74%, white);
  border-radius: inherit;
  box-shadow: 0 0 0 1px rgba(255,255,255,.24), 0 0 28px rgba(66,245,255,.5), 0 18px 44px rgba(0,0,0,.72);
  content: "";
  inset: -2px;
  pointer-events: none;
  position: absolute;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-performance="off"][data-pdc-grid-motion="on"][data-pdc-grid-scene="orbit"] [data-pdc-obsidian-distance="-1"],
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-performance="off"][data-pdc-grid-motion="on"][data-pdc-grid-scene="constellation"] [data-pdc-obsidian-distance="-1"] {
  filter: saturate(1.04) brightness(.94);
  transform: translate3d(-8px,-3px,0) scale(.985) !important;
  transition: transform 300ms var(--pdc-obsidian-ease), filter 220ms ease !important;
  z-index: 7 !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-performance="off"][data-pdc-grid-motion="on"][data-pdc-grid-scene="orbit"] [data-pdc-obsidian-distance="1"],
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-performance="off"][data-pdc-grid-motion="on"][data-pdc-grid-scene="constellation"] [data-pdc-obsidian-distance="1"] {
  filter: saturate(1.04) brightness(.94);
  transform: translate3d(8px,-3px,0) scale(.985) !important;
  transition: transform 300ms var(--pdc-obsidian-ease), filter 220ms ease !important;
  z-index: 7 !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-performance="off"][data-pdc-grid-motion="on"][data-pdc-grid-scene="constellation"] [data-pdc-obsidian-distance="-2"] {
  filter: saturate(.9) brightness(.78);
  transform: translate3d(-4px,3px,0) scale(.965) !important;
  transition: transform 340ms var(--pdc-obsidian-ease), filter 260ms ease !important;
  z-index: 4 !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-performance="off"][data-pdc-grid-motion="on"][data-pdc-grid-scene="constellation"] [data-pdc-obsidian-distance="2"] {
  filter: saturate(.9) brightness(.78);
  transform: translate3d(4px,3px,0) scale(.965) !important;
  transition: transform 340ms var(--pdc-obsidian-ease), filter 260ms ease !important;
  z-index: 4 !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-performance="off"][data-pdc-detail-transition="fade"][data-pdc-steam-surface="game-details"]:is([data-pdc-engine-budget="balanced"],[data-pdc-engine-budget="cinematic"]) #Main {
  animation: pdc-obsidian-arrive var(--hob-details-duration, 520ms) var(--pdc-obsidian-ease) both;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-performance="off"][data-pdc-steam-surface="settings"] [role="tab"].gpfocus,
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-performance="off"][data-pdc-steam-surface="settings"] [role="button"].gpfocus {
  box-shadow: 0 0 0 1px rgba(255,255,255,.32), 0 0 24px rgba(255,47,177,.42) !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-performance="off"][data-pdc-steam-surface="settings"][data-pdc-settings-scene="comet"][data-pdc-settings-comet="active"]:is([data-pdc-engine-budget="balanced"],[data-pdc-engine-budget="cinematic"]) .PageListColumn::before {
  background: linear-gradient(180deg, transparent, var(--pdc-obsidian-magenta) 28%, var(--pdc-obsidian-cyan) 72%, transparent);
  border-radius: 999px;
  box-shadow: 0 0 10px rgba(255,47,177,.72), 0 0 24px rgba(66,245,255,.58);
  content: "";
  height: var(--pdc-settings-comet-height);
  left: 6px;
  pointer-events: none;
  position: fixed;
  top: calc(var(--pdc-settings-comet-y) - var(--pdc-settings-comet-height) / 2);
  transition: top 240ms var(--pdc-obsidian-ease), height 180ms ease;
  width: 4px;
  z-index: 20;
}
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-motion="paused"] #pdc-obsidian-bloom-stage *,
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-motion="paused"] #pdc-obsidian-portal,
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-motion="paused"] #pdc-obsidian-portal *,
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-motion="paused"] [data-pdc-obsidian-focus],
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-motion="paused"] [data-pdc-obsidian-distance],
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-motion="paused"] .PageListColumn::before,
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-motion="paused"] #pdc-horizon-dossier *,
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-motion="paused"] #Main[data-pdc-horizon-dossier="true"] *,
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-motion="reduced"] #pdc-obsidian-bloom-stage *,
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-motion="reduced"] #pdc-obsidian-portal,
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-motion="reduced"] #pdc-obsidian-portal *,
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-motion="reduced"] [data-pdc-obsidian-focus],
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-motion="reduced"] [data-pdc-obsidian-distance],
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-motion="reduced"] .PageListColumn::before,
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-motion="reduced"] #pdc-horizon-dossier *,
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-motion="reduced"] #Main[data-pdc-horizon-dossier="true"] *,
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-motion-intensity="reduced"] #pdc-obsidian-bloom-stage *,
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-motion-intensity="reduced"] #pdc-obsidian-portal,
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-motion-intensity="reduced"] #pdc-obsidian-portal *,
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-motion-intensity="reduced"] [data-pdc-obsidian-focus],
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-motion-intensity="reduced"] [data-pdc-obsidian-distance],
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-motion-intensity="reduced"] .PageListColumn::before,
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-motion-intensity="reduced"] #pdc-horizon-dossier *,
html[data-pdc-theme-runtime="obsidian-bloom"][data-pdc-motion-intensity="reduced"] #Main[data-pdc-horizon-dossier="true"] * {
  animation-duration: .001ms !important;
  animation-iteration-count: 1 !important;
  scroll-behavior: auto !important;
  transition-duration: .001ms !important;
}
html[data-pdc-theme-runtime="obsidian-bloom"]:is([data-pdc-motion="paused"],[data-pdc-motion="reduced"],[data-pdc-motion-intensity="reduced"]) #pdc-obsidian-portal::before,
html[data-pdc-theme-runtime="obsidian-bloom"]:is([data-pdc-motion="paused"],[data-pdc-motion="reduced"],[data-pdc-motion-intensity="reduced"]) #pdc-obsidian-portal::after {
  animation-duration: .001ms !important;
  animation-iteration-count: 1 !important;
}
@keyframes pdc-obsidian-arrive {
  from { opacity: .42; transform: translate3d(0,16px,0) scale(.992); }
  to { opacity: 1; transform: none; }
}
@keyframes pdc-obsidian-portal-entry-veil {
  from { opacity: .12; }
  58% { opacity: .72; }
  to { opacity: .62; }
}
@keyframes pdc-obsidian-portal-entry-echo {
  from { opacity: .05; transform: scale(1.09); }
  to { opacity: .2; transform: scale(1.02); }
}
@keyframes pdc-obsidian-portal-entry-artwork {
  0% { opacity: 1; transform: translate3d(-50%,-50%,0) scale(1); }
  18% { opacity: 1; transform: translate3d(-50%,calc(-50% - 12px),0) scale(1.035); }
  76%,100% {
    opacity: 1;
    transform: translate3d(calc(-50% + var(--pdc-portal-dock-dx)),calc(-50% + var(--pdc-portal-dock-dy)),0) scale(var(--pdc-portal-dock-scale));
  }
}
@keyframes pdc-obsidian-portal-exit-veil {
  from { opacity: .84; }
  to { opacity: 1; }
}
@keyframes pdc-obsidian-portal-exit-echo {
  from { opacity: .12; transform: scale(1); }
  to { opacity: .2; transform: scale(1.035); }
}
@keyframes pdc-obsidian-portal-return-veil {
  from { opacity: 1; }
  64% { opacity: .38; }
  to { opacity: 0; }
}
@keyframes pdc-obsidian-portal-return-echo {
  from { opacity: .2; transform: scale(1.035); }
  to { opacity: 0; transform: scale(1); }
}
@keyframes pdc-obsidian-portal-return-artwork {
  from { opacity: 1; transform: translate3d(-50%,-50%,0) scale(1); }
  to {
    opacity: 1;
    transform: translate3d(calc(-50% + var(--pdc-portal-target-dx)),calc(-50% + var(--pdc-portal-target-dy)),0) scale(var(--pdc-portal-target-scale));
  }
}
${HORIZON_DOSSIER_CSS}
${ORBITAL_ABYSS_CSS}`;

function isDocumentElement(value: unknown, doc: Document): value is Element {
  const ElementType = doc.defaultView?.Element;
  return typeof ElementType === "function" && value instanceof ElementType;
}

function artworkFrom(element: Element, doc: Document): string | null {
  const image = element.matches("img") ? element : element.querySelector("img");
  const ImageElement = doc.defaultView?.HTMLImageElement;
  if (typeof ImageElement !== "function" || !(image instanceof ImageElement)) return null;
  return safeArtworkUrl(image.currentSrc || image.src);
}

function focusedGameCard(target: Element): Element | null {
  return target.closest(GAME_CARD_SELECTOR) ?? target.closest(GAME_LINK_SELECTOR);
}

function restoreAttribute(root: HTMLElement, name: string, previous: string | null): void {
  if (previous === null) root.removeAttribute(name);
  else root.setAttribute(name, previous);
}

export function createObsidianBloomRuntime(doc: Document = document): ThemeRuntimeModule {
  return {
    id: "obsidian-bloom",
    mount(theme) {
      const root = doc.documentElement;
      const win = doc.defaultView;
      if (
        !win
        || typeof win.MutationObserver !== "function"
        || typeof win.requestAnimationFrame !== "function"
        || typeof win.cancelAnimationFrame !== "function"
        || doc.getElementById(STYLE_ID)
      ) return () => {};

      const previousRuntime = root.getAttribute("data-pdc-theme-runtime");
      const previousSurface = root.getAttribute("data-pdc-steam-surface");
      const previousMotion = root.getAttribute("data-pdc-motion");
      const previousGridMotion = root.getAttribute("data-pdc-grid-motion");
      const previousMotionIntensity = root.getAttribute("data-pdc-motion-intensity");
      const previousAdaptiveBackdrop = root.getAttribute("data-pdc-adaptive-backdrop");
      const previousPerformance = root.getAttribute("data-pdc-performance");
      const previousArtwork = root.style.getPropertyValue("--pdc-obsidian-artwork");
      const previousLibraryScene = root.getAttribute("data-pdc-library-scene");
      const previousGridScene = root.getAttribute("data-pdc-grid-scene");
      const previousDetailTransition = root.getAttribute("data-pdc-detail-transition");
      const previousSettingsScene = root.getAttribute("data-pdc-settings-scene");
      const previousEngineBudget = root.getAttribute("data-pdc-engine-budget");
      const previousOrbitRestoring = root.getAttribute("data-pdc-orbit-restoring");
      const config = obsidianConfigFromTheme(theme);
      const style = doc.createElement("style");
      style.id = STYLE_ID;
      style.textContent = RUNTIME_CSS;
      doc.head.append(style);
      root.dataset.pdcThemeRuntime = "obsidian-bloom";
      root.dataset.pdcGridMotion = config.gridMotion ? "on" : "off";
      root.dataset.pdcMotionIntensity = config.motionIntensity;
      root.dataset.pdcAdaptiveBackdrop = config.adaptiveBackdrop;
      root.dataset.pdcPerformance = config.performance ? "on" : "off";
      root.dataset.pdcLibraryScene = config.libraryScene;
      root.dataset.pdcGridScene = config.gridScene;
      root.dataset.pdcDetailTransition = config.detailTransition;
      root.dataset.pdcSettingsScene = config.settingsScene;

      let focused: Element | null = null;
      let dossierArtwork: string | null = null;
      let stopped = false;
      let engineBudget: EngineBudget = "suspended";
      let currentSurface: ThemeRuntimeSurface | null = null;
      let currentMain: Element | null = null;
      const refreshMotion = () => {
        const reduced = media?.matches ?? false;
        root.dataset.pdcMotion = doc.hidden ? "paused" : reduced ? "reduced" : "full";
      };
      const clearLibraryFocus = () => {
        focused?.removeAttribute("data-pdc-obsidian-focus");
        constellationFocus?.clear();
        orbitalAbyss?.clear();
        focused = null;
      };
      const rememberArtworkFor = (element: Element) => {
        const artwork = artworkFrom(element, doc);
        if (!artwork) return;
        dossierArtwork = artwork;
        root.style.setProperty("--pdc-obsidian-artwork", `url(${JSON.stringify(artwork)})`);
        const rect = element.getBoundingClientRect();
        const validRect = [rect.left, rect.top, rect.width, rect.height].every(Number.isFinite)
          && rect.width > 0
          && rect.height > 0;
        if (!validRect) return;
        portalTransition?.remember(artwork, rect);
        if (config.adaptiveBackdrop !== "off") bloomStage?.update(artwork, rect);
      };
      const focusTarget = (target: Element) => {
        const next = focusedGameCard(target);
        const librarySurface = currentSurface === "library" || currentSurface === "library-grid";
        const engineAvailable = engineBudget === "balanced" || engineBudget === "cinematic";
        const selectionIntact = next === focused && (orbitalAbyss
          ? root.dataset.pdcOrbitActive === "true"
          : next?.getAttribute("data-pdc-obsidian-focus") === "true");
        if (librarySurface && next && engineAvailable && selectionIntact) {
          rememberArtworkFor(next);
          return;
        }
        clearLibraryFocus();
        if (!librarySurface || !next || !engineAvailable) return;
        focused = next;
        if (orbitalAbyss) {
          if (!orbitalAbyss.moveTo(focused)) {
            focused.setAttribute("data-pdc-obsidian-focus", "true");
          }
        } else {
          focused.setAttribute("data-pdc-obsidian-focus", "true");
          constellationFocus?.moveTo(focused);
        }
        rememberArtworkFor(focused);
      };
      const onFocus = (event: Event) => {
        if (isDocumentElement(event.target, doc)) focusTarget(event.target);
      };

      const media = win.matchMedia?.("(prefers-reduced-motion: reduce)");
      let stopSurfaceSession: (() => void) | null = null;
      let bloomStage: BloomStage | null = null;
      let constellationFocus: ConstellationFocus | null = null;
      let orbitalAbyss: OrbitalAbyss | null = null;
      let portalTransition: PortalTransition | null = null;
      let horizonDossier: HorizonDossier | null = null;
      let stopSettingsComet: (() => void) | null = null;
      let stopEngineGovernor: (() => void) | null = null;
      let orbitRestoreFrame = 0;
      let orbitRestoreTimer = 0;
      let portalEntryPending = false;
      const engineAvailable = () => engineBudget === "balanced" || engineBudget === "cinematic";
      const restoreOrbitRestoring = () => {
        if (orbitRestoreFrame) win.cancelAnimationFrame(orbitRestoreFrame);
        if (orbitRestoreTimer) win.clearTimeout(orbitRestoreTimer);
        orbitRestoreFrame = 0;
        orbitRestoreTimer = 0;
        restoreAttribute(root, "data-pdc-orbit-restoring", previousOrbitRestoring);
      };
      const armOrbitRestoring = () => {
        if (orbitRestoreFrame) win.cancelAnimationFrame(orbitRestoreFrame);
        if (orbitRestoreTimer) win.clearTimeout(orbitRestoreTimer);
        orbitRestoreFrame = 0;
        root.dataset.pdcOrbitRestoring = "true";
        orbitRestoreTimer = win.setTimeout(() => {
          orbitRestoreTimer = 0;
          restoreOrbitRestoring();
        }, ORBIT_RESTORE_TIMEOUT_MS);
      };
      const releaseOrbitRestoringAfterPaint = (main: Element | null) => {
        if (orbitRestoreFrame) win.cancelAnimationFrame(orbitRestoreFrame);
        let framesRemaining = ORBIT_SETTLE_MAX_FRAMES;
        const settle = () => {
          orbitRestoreFrame = 0;
          if (currentSurface !== "library" && currentSurface !== "library-grid") {
            restoreOrbitRestoring();
            return;
          }
          const activeFocus = main?.querySelector(".gpfocus");
          if (activeFocus) focusTarget(activeFocus);
          const settled = root.dataset.pdcOrbitActive === "true"
            && Boolean(main?.querySelector('[data-pdc-orbit-selected="true"]'));
          if (settled) {
            orbitRestoreFrame = win.requestAnimationFrame(() => {
              orbitRestoreFrame = 0;
              portalTransition?.completeExit();
            });
            return;
          }
          if (framesRemaining <= 0) {
            portalTransition?.completeExit();
            return;
          }
          framesRemaining -= 1;
          orbitRestoreFrame = win.requestAnimationFrame(settle);
        };
        orbitRestoreFrame = win.requestAnimationFrame(settle);
      };
      const reconcileDossier = () => {
        if (
          config.detailTransition === "portal"
          && !config.performance
          && engineAvailable()
          && currentSurface === "game-details"
          && currentMain
        ) {
          if (horizonDossier?.show(currentMain, dossierArtwork)) {
            if (portalEntryPending) {
              portalEntryPending = false;
              portalTransition?.completeEntry();
            }
            return;
          }
        }
        horizonDossier?.clear();
      };
      const onActivate = (event: Event) => {
        if (
          currentSurface !== "library"
          && currentSurface !== "library-grid"
        ) return;
        if (!portalTransition || !engineAvailable()) return;
        const mouse = event as MouseEvent;
        if (typeof mouse.button === "number" && mouse.button !== 0) return;
        if (!isDocumentElement(event.target, doc)) return;
        const card = focusedGameCard(event.target);
        if (!card || card !== focused) return;
        const artwork = artworkFrom(card, doc);
        const rect = card.getBoundingClientRect();
        if (!artwork || rect.width <= 0 || rect.height <= 0) return;
        portalEntryPending = true;
        portalTransition.remember(artwork, rect);
        portalTransition.beginEntry();
      };
      const onKeyDown = (event: Event) => {
        if ((event as KeyboardEvent).key !== "Escape" || currentSurface !== "game-details") return;
        if (!portalTransition || !engineAvailable()) return;
        const target = isDocumentElement(event.target, doc) ? event.target : null;
        const active = isDocumentElement(doc.activeElement, doc) ? doc.activeElement : null;
        if (target?.closest('[role="dialog"]') || active?.closest('[role="dialog"]')) return;
        armOrbitRestoring();
        portalTransition.beginExit();
      };
      const stop = () => {
        if (stopped) return;
        stopped = true;
        stopSurfaceSession?.();
        horizonDossier?.dispose();
        bloomStage?.dispose();
        constellationFocus?.dispose();
        orbitalAbyss?.dispose();
        portalTransition?.dispose();
        stopSettingsComet?.();
        stopEngineGovernor?.();
        media?.removeEventListener?.("change", refreshMotion);
        doc.removeEventListener("visibilitychange", refreshMotion);
        doc.removeEventListener("focusin", onFocus, true);
        doc.removeEventListener("click", onActivate, true);
        doc.removeEventListener("keydown", onKeyDown, true);
        focused?.removeAttribute("data-pdc-obsidian-focus");
        style.remove();
        restoreAttribute(root, "data-pdc-theme-runtime", previousRuntime);
        restoreAttribute(root, "data-pdc-steam-surface", previousSurface);
        restoreAttribute(root, "data-pdc-motion", previousMotion);
        restoreAttribute(root, "data-pdc-grid-motion", previousGridMotion);
        restoreAttribute(root, "data-pdc-motion-intensity", previousMotionIntensity);
        restoreAttribute(root, "data-pdc-adaptive-backdrop", previousAdaptiveBackdrop);
        restoreAttribute(root, "data-pdc-performance", previousPerformance);
        restoreAttribute(root, "data-pdc-library-scene", previousLibraryScene);
        restoreAttribute(root, "data-pdc-grid-scene", previousGridScene);
        restoreAttribute(root, "data-pdc-detail-transition", previousDetailTransition);
        restoreAttribute(root, "data-pdc-settings-scene", previousSettingsScene);
        restoreAttribute(root, "data-pdc-engine-budget", previousEngineBudget);
        restoreOrbitRestoring();
        portalEntryPending = false;
        dossierArtwork = null;
        if (previousArtwork) root.style.setProperty("--pdc-obsidian-artwork", previousArtwork);
        else root.style.removeProperty("--pdc-obsidian-artwork");
      };

      try {
        media?.addEventListener?.("change", refreshMotion);
        doc.addEventListener("visibilitychange", refreshMotion);
        doc.addEventListener("focusin", onFocus, true);
        doc.addEventListener("click", onActivate, true);
        doc.addEventListener("keydown", onKeyDown, true);
        if (!config.performance && config.adaptiveBackdrop !== "off") {
          bloomStage = startBloomStage(doc);
        }
        if (!config.performance && config.gridMotion) {
          if (config.gridScene === "abyss") orbitalAbyss = startOrbitalAbyss(doc);
          else constellationFocus = startConstellationFocus(config.gridScene);
        }
        if (!config.performance && config.detailTransition === "portal") {
          portalTransition = startPortalTransition(doc);
          horizonDossier = startHorizonDossier(doc);
        }
        if (!config.performance && config.settingsScene === "comet") {
          stopSettingsComet = startSettingsComet(doc);
        }
        stopEngineGovernor = startEngineGovernor({
          doc,
          performance: config.performance,
          motionIntensity: config.motionIntensity,
          media,
          onBudget(budget) {
            engineBudget = budget;
            root.dataset.pdcEngineBudget = budget;
            if (budget === "efficient" || budget === "suspended") {
              focused?.removeAttribute("data-pdc-obsidian-focus");
              constellationFocus?.clear();
              orbitalAbyss?.clear();
              portalTransition?.surfaceChanged(null);
              horizonDossier?.clear();
              restoreOrbitRestoring();
            } else {
              portalTransition?.surfaceChanged(currentSurface);
              reconcileDossier();
            }
          },
        });
        stopSurfaceSession = startSteamSurfaceSession({
          doc,
          onSurface(surface, main) {
            const previousDetectedSurface = currentSurface;
            const enteringDetails = previousDetectedSurface !== "game-details" && surface === "game-details";
            const returningToLibrary = previousDetectedSurface === "game-details"
              && (surface === "library" || surface === "library-grid");
            if (returningToLibrary && root.dataset.pdcOrbitRestoring !== "true") {
              armOrbitRestoring();
              if (engineAvailable()) portalTransition?.beginExit();
            }
            currentSurface = surface;
            currentMain = main;
            if (enteringDetails) portalEntryPending = true;
            if (surface !== "game-details") {
              portalEntryPending = false;
            }
            if (surface) root.dataset.pdcSteamSurface = surface;
            else root.removeAttribute("data-pdc-steam-surface");
            if (engineBudget === "balanced" || engineBudget === "cinematic") {
              portalTransition?.surfaceChanged(surface);
            } else {
              portalTransition?.surfaceChanged(null);
            }
            if (surface !== "library" && surface !== "library-grid") clearLibraryFocus();
            else {
              const activeFocus = main?.querySelector(".gpfocus");
              if (activeFocus) focusTarget(activeFocus);
              if (returningToLibrary) releaseOrbitRestoringAfterPaint(main);
            }
            reconcileDossier();
          },
        });
        refreshMotion();
        return stop;
      } catch (error) {
        stop();
        throw error;
      }
    },
  };
}
