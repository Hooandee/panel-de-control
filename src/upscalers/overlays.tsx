import { findSP } from "@decky/ui";
import { useEffect, useMemo, useRef, useState, type FC } from "react";
import { createPortal } from "react-dom";

import { getUpscalersOverview } from "../api";
import { useI18n } from "../i18n";
import { registerGlobal } from "../platform/globalComponent";
import { OverGameComposition } from "../platform/overGameComposition";
import { subscribeQamSurface, type QamSurface } from "../platform/qamSurface";
import { readString, writeString } from "../system/pdcStorage";
import { useRunningGame } from "../tdp/useRunningGame";
import { useGameInFront } from "./gameInFront";
import { useOverlayLive } from "./useOverlayLive";
import { startFpsCounterSession } from "./fpsCounter";
import { badgeLabel } from "./model";
import type { BuildInfo, UpscalersOverview } from "./types";

export type InGameMode = "off" | "start" | "always";
export const IN_GAME_MODES: InGameMode[] = ["off", "start", "always"];

const IN_GAME_KEY = "pdc:upscalers:inGame";
const COVERS_KEY = "pdc:upscalers:covers";
const START_MS = 6000;
const OVERVIEW_RETRY_MS = [2000, 5000, 15000, 30000, 60000];
const STYLE_ID = "pdc-up-cover-style";
const HOST_ID = "pdc-up-ingame";
const COVER_IMAGE = /\/(?:assets|customimages|apps)\/(\d+)(?:\/|p\.|\.)/;

type ProviderFamily = "fsr" | "xess" | "dlss";
const PROVIDER_NAMES: Record<ProviderFamily, string> = { fsr: "FSR", xess: "XeSS", dlss: "DLSS" };

function providerOf(build: BuildInfo | undefined): ProviderFamily | null {
  if (!build) return null;
  return build.family === "xess" ? "xess" : "fsr";
}

interface Badge {
  label: string;
  short: string;
  state: string;
  build: string;
  engine: string | null;
  provider: ProviderFamily | null;
  fg: boolean;
  fgRoute: string | null;
}

let installs: Record<string, Badge> = {};
// Covers also name what runs without an upscaler install: Mako's spatial scaling or a frame generator on its own.
let engineCovers: Record<string, Badge> = {};
let sectionOpen = false;
let ghost: { image: string; opacity: number } | null = null;
const listeners = new Set<() => void>();

function emit(): void {
  for (const listener of listeners) listener();
}

/** Publishes what Escaladores knows so covers and the in-game pill follow it without polling. */
export function publishOverview(overview: UpscalersOverview): void {
  const next: Record<string, Badge> = {};
  for (const [appid, install] of Object.entries(overview.installs)) {
    const build = overview.builds.find((b) => b.id === install.build);
    const label = badgeLabel(build, install.options?.model, install.build);
    next[appid] = { label: label.full, short: label.short, state: install.status, build: install.build, engine: build?.engine ?? null, provider: providerOf(build), fg: install.options?.fg === "on", fgRoute: install.options?.fg_route ?? null };
  }
  installs = next;
  const covers: Record<string, Badge> = {};
  for (const [appid, engines] of Object.entries(overview.engines ?? {})) {
    if (next[appid]) continue;
    const label = engines.mako?.spatial ? "Mako"
      : engines.mako?.fg ? `Mako${engines.mako.multiplier ? ` ×${engines.mako.multiplier}` : ""}`
      : engines.lossless ? `Lossless${engines.lossless.multiplier ? ` ×${engines.lossless.multiplier}` : ""}` : null;
    if (label) covers[appid] = { label, short: label, state: "pending", build: label.toLowerCase(), engine: null, provider: null, fg: false, fgRoute: null };
  }
  engineCovers = covers;
  emit();
}

const NO_COVERS: Record<string, Badge> = {};

function useCoverLabels(): Record<string, Badge> {
  const installed = useInstalls();
  const [engines, setEngines] = useState(engineCovers);
  const [shown, setShown] = useState(readCoverBadges);
  useEffect(() => {
    const update = () => { setEngines(engineCovers); setShown(readCoverBadges()); };
    update();
    listeners.add(update);
    return () => { listeners.delete(update); };
  }, []);
  return useMemo(() => shown ? { ...engines, ...installed } : NO_COVERS, [engines, installed, shown]);
}

/** Games with a Panel upscaler or engine profile, for a report to describe. */
export function reportedAppids(): string[] {
  return [...new Set([...Object.keys(installs), ...Object.keys(engineCovers)])];
}

export function useInstalls(): Record<string, Badge> {
  const [value, setValue] = useState(installs);
  useEffect(() => {
    const update = () => setValue(installs);
    // A publish between the first render and this effect would otherwise be lost until the next one.
    update();
    listeners.add(update);
    return () => { listeners.delete(update); };
  }, []);
  return value;
}

/** The first comparison shot drawn over the game so the second can be framed the same way. */
export function setCompareGhost(next: { image: string; opacity: number } | null): void {
  ghost = next;
  emit();
}

/** While Escaladores is on screen the pill stays up, whatever the mode, so the user can see what runs. */
export function setUpscalersSectionOpen(open: boolean): void {
  sectionOpen = open;
  emit();
}

export function readInGameMode(): InGameMode {
  const value = readString(IN_GAME_KEY);
  return IN_GAME_MODES.includes(value as InGameMode) ? (value as InGameMode) : "off";
}

export function writeInGameMode(mode: InGameMode): void {
  writeString(IN_GAME_KEY, mode);
  emit();
}

export function readCoverBadges(): boolean {
  return readString(COVERS_KEY) !== "off";
}

export function writeCoverBadges(shown: boolean): void {
  writeString(COVERS_KEY, shown ? "on" : "off");
  emit();
}

function mainWindow(): Window | null {
  try {
    return findSP() ?? null;
  } catch {
    return null;
  }
}

const BADGE_CLASS = "pdc-up-badge";
const HOST_ATTR = "data-pdc-up-host";
const GLYPH = `<svg viewBox="0 0 24 24" width="1em" height="1em" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 3 9 15"/><path d="M12 3H3v18h18v-9"/><path d="M16 3h5v5"/><path d="M14 15H9v-5"/></svg>`;
// Logos and blurred backdrops are never the tile itself; icons count only as round tiles (bubbles).
const NOT_TILE = /logo|_hero_blur/i;
const ICON = /icon|\/community_assets\//i;

const COVER_CSS = `
[${HOST_ATTR}="relative"] { position: relative; }
.${BADGE_CLASS} {
  position: absolute; z-index: 3; top: var(--pdc-up-inset, 6px); left: var(--pdc-up-inset, 6px);
  display: inline-flex; align-items: center; gap: 5px; max-width: calc(100% - 2 * var(--pdc-up-inset, 6px));
  padding: 3px 9px 3px 6px; border-radius: 999px; box-sizing: border-box;
  font: 700 11px/15px "Motiva Sans", "Noto Sans", Arial, sans-serif; letter-spacing: .15px; white-space: nowrap;
  color: #f4f7fb; background: rgba(14, 17, 24, .82);
  -webkit-backdrop-filter: blur(10px) saturate(1.4); backdrop-filter: blur(10px) saturate(1.4);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, .14), 0 3px 10px rgba(0, 0, 0, .38);
  pointer-events: none; overflow: hidden; text-overflow: ellipsis;
  transform-origin: top left; animation: pdc-up-badge-in 260ms cubic-bezier(.2, .8, .2, 1) both;
}
.${BADGE_CLASS} > svg { flex: none; font-size: 12px; color: #9fb4c8; }
.${BADGE_CLASS} > b { font-weight: 700; overflow: hidden; text-overflow: ellipsis; }
.${BADGE_CLASS}[data-state="active"] > svg { color: #6fe3a1; }
.${BADGE_CLASS}[data-state="active"] { box-shadow: inset 0 0 0 1px rgba(111, 227, 161, .55), 0 3px 10px rgba(0, 0, 0, .38); }
.${BADGE_CLASS}[data-state="broken"] > svg, .${BADGE_CLASS}[data-state="broken"] > b { color: #ffbe63; }
.${BADGE_CLASS}[data-state="broken"] { box-shadow: inset 0 0 0 1px rgba(255, 190, 99, .6), 0 3px 10px rgba(0, 0, 0, .38); }
.${BADGE_CLASS}[data-size="s"] { padding: 2px 7px 2px 5px; gap: 4px; font-size: 9.5px; line-height: 13px; }
.${BADGE_CLASS}[data-size="s"] > svg { font-size: 10px; }
.${BADGE_CLASS}[data-round] { top: auto; left: 50%; bottom: 4%; transform: translateX(-50%); animation-name: pdc-up-badge-in-round; }
@keyframes pdc-up-badge-in-round { from { opacity: 0; transform: translateX(-50%) scale(.88); } to { opacity: 1; transform: translateX(-50%); } }
@keyframes pdc-up-badge-in { from { opacity: 0; transform: scale(.88); } to { opacity: 1; transform: none; } }
`;

function appidOf(src: string): string | null {
  return src.match(COVER_IMAGE)?.[1] ?? null;
}

/**
 * Where the pill goes: the box wrapping the image itself. Steam and the themes lift the focused tile with a
 * z-index on an inner wrapper, so a pill on an outer wrapper ends up underneath it.
 */
export function hostOf(img: HTMLImageElement, tile: HTMLElement): HTMLElement {
  const parent = img.parentElement;
  if (!parent || !tile.contains(parent)) return tile;
  // A wrapper taller or wider than the tile is cropped by it (Eclipse's orbs): the pill would fall outside.
  const inner = parent.getBoundingClientRect();
  const outer = tile.getBoundingClientRect();
  return inner.width > outer.width * 1.15 + 8 || inner.height > outer.height * 1.15 + 8 ? tile : parent;
}

/** A collection's collage: the one selectable item around the art shows several games. */
export function isCollection(tile: HTMLElement): boolean {
  let item: HTMLElement | null = tile;
  for (let depth = 0; item && depth < 8 && !item.classList.contains("Focusable"); depth++) item = item.parentElement;
  if (!item?.classList.contains("Focusable")) return false;
  // Themes that draw their own cards make a whole row or screen one selectable item; that is not a collage.
  const own = tile.getBoundingClientRect();
  const outer = item.getBoundingClientRect();
  if (outer.width > own.width * 2.5 || outer.height > own.height * 2.5) return false;
  // Gallery makes its whole carousel, neighbours included, one selectable item; a collection is never screen-wide.
  const view = tile.ownerDocument.defaultView;
  if (view && outer.width >= view.innerWidth * 0.9) return false;
  const appids = new Set<string>();
  for (const img of Array.from(item.querySelectorAll("img"))) {
    const appid = appidOf(img.src);
    if (appid) appids.add(appid);
    if (appids.size > 1) return true;
  }
  return false;
}

/** The visible tile an image belongs to: its ancestors while they stay the image's size, as every theme wraps art. */
export function tileOf(img: HTMLImageElement): HTMLElement | null {
  const box = img.getBoundingClientRect();
  let tile: HTMLElement | null = img.parentElement;
  if (!tile) return null;
  for (let depth = 0; depth < 5; depth++) {
    const parent: HTMLElement | null = tile.parentElement;
    if (!parent || parent === img.ownerDocument.body) break;
    const outer = parent.getBoundingClientRect();
    if (outer.width > box.width * 1.15 + 8 || outer.height > box.height * 1.15 + 8) break;
    // Collapsed layout wrappers (0×0 grid cells) are not the card.
    if (outer.width < box.width * 0.5 || outer.height < box.height * 0.5) break;
    tile = parent;
  }
  return tile;
}

/** Art a theme keeps in the tree but out of sight (Gallery hides Steam's own image under the copy it draws). */
export function isHidden(img: HTMLElement, view: Window): boolean {
  let opacity = 1;
  let node: HTMLElement | null = img;
  for (let depth = 0; node && depth < 8 && node !== img.ownerDocument.body; depth++, node = node.parentElement) {
    const style = view.getComputedStyle(node);
    if (style.visibility === "hidden" || style.display === "none") return true;
    const own = parseFloat(style.opacity);
    opacity *= Number.isNaN(own) ? 1 : own;
    if (opacity < 0.05) return true;
  }
  return false;
}

function isRound(tile: HTMLElement, view: Window): boolean {
  const radius = view.getComputedStyle(tile).borderTopLeftRadius;
  return radius.endsWith("%") ? parseFloat(radius) >= 35 : parseFloat(radius) >= tile.getBoundingClientRect().width * 0.35;
}

function placeBadge(host: HTMLElement, tile: HTMLElement, badge: Badge, view: Window): void {
  let node = host.querySelector<HTMLElement>(`:scope > .${BADGE_CLASS}`);
  if (!node) {
    node = host.ownerDocument.createElement("span");
    node.className = BADGE_CLASS;
    host.appendChild(node);
  }
  const width = tile.getBoundingClientRect().width;
  const small = width < 150;
  const text = small ? badge.short : badge.label;
  if (node.getAttribute("data-label") !== text) {
    node.setAttribute("data-label", text);
    node.innerHTML = `${GLYPH}<b></b>`;
    node.querySelector("b")!.textContent = text;
  }
  if (node.getAttribute("data-state") !== badge.state) node.setAttribute("data-state", badge.state);
  if (node.getAttribute("data-size") !== (small ? "s" : "m")) node.setAttribute("data-size", small ? "s" : "m");
  const style = view.getComputedStyle(tile);
  if (view.getComputedStyle(host).position === "static" && host.getAttribute(HOST_ATTR) !== "relative") host.setAttribute(HOST_ATTR, "relative");
  else if (!host.hasAttribute(HOST_ATTR)) host.setAttribute(HOST_ATTR, "own");
  // Keep the pill inside rounded corners, whatever radius the theme gives its tiles; on round tiles it sits at the bottom.
  const radius = parseFloat(style.borderTopLeftRadius) || 0;
  const round = isRound(tile, view);
  if (round !== node.hasAttribute("data-round")) node.toggleAttribute("data-round", round);
  const inset = `${Math.round(Math.max(6, Math.min(14, radius * 0.45 + 4)))}px`;
  if (node.style.getPropertyValue("--pdc-up-inset") !== inset) node.style.setProperty("--pdc-up-inset", inset);
}

function clearBadge(tile: Element): void {
  tile.querySelector(`:scope > .${BADGE_CLASS}`)?.remove();
  tile.removeAttribute(HOST_ATTR);
}

/** Puts a pill on every tile showing a game's art, in Steam's library and in any theme that draws its own tiles. */
export const CoverBadges: FC = () => {
  const map = useCoverLabels();
  useEffect(() => {
    const view = mainWindow();
    const doc = view?.document;
    if (!view || !doc?.body) return;
    let style = doc.getElementById(STYLE_ID);
    if (!style) {
      style = doc.createElement("style");
      style.id = STYLE_ID;
      doc.head.appendChild(style);
    }
    style.textContent = COVER_CSS;
    let pending = 0;
    const mark = () => {
      pending = 0;
      const limit = view.innerWidth * 0.6;
      // A tile can hold several copies of the art (Gallery's reflection, crossfade layers); the largest is the face.
      const faces = new Map<HTMLElement, { img: HTMLImageElement; badge: Badge; area: number }>();
      for (const img of Array.from(doc.querySelectorAll<HTMLImageElement>("img[src*='/assets/'], img[src*='/customimages/'], img[src*='/apps/']"))) {
        const appid = appidOf(img.src);
        if (!appid || NOT_TILE.test(img.src)) continue;
        const badge = map[appid];
        if (!badge) continue;
        const box = img.getBoundingClientRect();
        if (box.width < 56 || box.height < 40 || box.width > limit) continue;
        const tile = tileOf(img);
        if (!tile) continue;
        // Art parked in a collapsed wrapper has no card to sit on; the pill would float on its own.
        const tileBox = tile.getBoundingClientRect();
        if (tileBox.width < box.width * 0.5 || tileBox.height < box.height * 0.5) continue;
        if (ICON.test(img.src) && !isRound(tile, view)) continue;
        if (isCollection(tile)) continue;
        if (isHidden(img, view)) continue;
        const area = box.width * box.height;
        const seen = faces.get(tile);
        if (!seen || area > seen.area) faces.set(tile, { img, badge, area });
      }
      // A tilted face can measure smaller than its card and count as a tile of its own; one pill per card.
      for (const [tile, face] of faces) {
        let up = tile.parentElement;
        for (let depth = 0; up && depth < 6; depth++, up = up.parentElement) {
          const outer = faces.get(up);
          if (!outer) continue;
          if (outer.area >= face.area) faces.delete(tile);
          else faces.delete(up);
          break;
        }
      }
      const hosts = new Set<Element>();
      for (const [tile, face] of faces) {
        const host = hostOf(face.img, tile);
        hosts.add(host);
        placeBadge(host, tile, face.badge, view);
      }
      for (const node of Array.from(doc.querySelectorAll(`.${BADGE_CLASS}`))) {
        if (node.parentElement && !hosts.has(node.parentElement)) clearBadge(node.parentElement);
      }
    };
    const schedule = () => {
      if (!pending) pending = view.setTimeout(mark, 180);
    };
    mark();
    const Observer = (view as Window & typeof globalThis).MutationObserver;
    const ours = (node: Node) => (node as Element).classList?.contains(BADGE_CLASS) ?? false;
    const observer = new Observer((records: MutationRecord[]) => {
      // Our own pills going in or out must not wake the observer again.
      const foreign = records.some((r) => r.type === "attributes"
        || [...Array.from(r.addedNodes), ...Array.from(r.removedNodes)].some((n) => !ours(n)));
      if (foreign) schedule();
    });
    observer.observe(doc.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["src"] });
    const settle = view.setInterval(mark, 1500);
    return () => {
      observer.disconnect();
      view.clearInterval(settle);
      if (pending) view.clearTimeout(pending);
      for (const node of Array.from(doc.querySelectorAll(`.${BADGE_CLASS}`))) {
        if (node.parentElement) clearBadge(node.parentElement);
      }
    };
  }, [map]);
  return null;
};

/** A short pill over the running game naming the upscaler Panel installed. Draw-only: input stays with the game. */
export const InGameBadge: FC = () => {
  const { t } = useI18n();
  const map = useInstalls();
  const running = useRunningGame();
  const gameInFront = useGameInFront();
  const [mode, setMode] = useState(readInGameMode);
  const [inSection, setInSection] = useState(sectionOpen);
  const [ghostShot, setGhostShot] = useState(ghost);
  const [surface, setSurface] = useState<QamSurface | null>(null);

  useEffect(() => subscribeQamSurface(setSurface), []);
  const [host, setHost] = useState<HTMLDivElement | null>(null);
  const badge = running ? map[String(running.liveAppid)] : undefined;
  const { live, lossless, makoResolutionWarning, makoMultiplier, makoSpatial } = useOverlayLive(running ? String(running.liveAppid) : null, !!badge);
  const resolution = live?.resolution ? [live.resolution.render[1], live.resolution.output[1]] : null;
  const installedDll = badge?.engine === "dll" && badge.state === "not_run";
  const hasContent = installedDll || !!live || !!lossless || makoResolutionWarning || makoMultiplier !== null || !!makoSpatial;
  const observedFamily = live?.provider_family ?? null;
  const otherProvider = !!observedFamily && !!badge?.provider && badge.engine !== "dll" && observedFamily !== badge.provider;
  const observedName = live?.provider_name ?? (observedFamily ? PROVIDER_NAMES[observedFamily] : null);
  const observedProvider = otherProvider
    ? [observedName, live?.provider_version].filter(Boolean).join(" ")
    : live?.provider_source === "optiscaler_log" && live.provider_name && live.provider_version
      ? `${live.provider_name} ${live.provider_version}` : null;
  const fgLabel = lossless
    ? `Lossless Scaling ×${lossless.multiplier} ${t(`up.lsfg.flow.${lossless.flow}`)}`
    : badge?.fg ? t(`up.fg.pick.${badge.fgRoute ?? "optiscaler"}`) : null;
  const fgState = lossless || live?.fg == null ? t("up.overlay.configured") : live.fg ? t("up.overlay.generating") : t("up.overlay.paused");

  useEffect(() => {
    const update = () => {
      setMode(readInGameMode());
      setInSection(sectionOpen);
      setGhostShot(ghost);
    };
    update();
    listeners.add(update);
    return () => { listeners.delete(update); };
  }, []);

  useEffect(() => {
    const doc = mainWindow()?.document;
    if (!doc?.body) return;
    doc.getElementById(HOST_ID)?.remove();
    const node = doc.createElement("div");
    node.id = HOST_ID;
    doc.body.appendChild(node);
    setHost(node);
    return () => { node.remove(); };
  }, []);

  const [startWindow, setStartWindow] = useState(false);
  const startedFor = useRef<number | null>(null);
  const startTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    startedFor.current = null;
    setStartWindow(false);
    return () => { if (startTimer.current) clearTimeout(startTimer.current); };
  }, [running?.liveAppid]);
  useEffect(() => {
    if (!hasContent || !running || startedFor.current === running.liveAppid) return;
    startedFor.current = running.liveAppid;
    setStartWindow(true);
    startTimer.current = setTimeout(() => setStartWindow(false), START_MS);
  }, [running?.liveAppid, hasContent]);

  const sectionShown = inSection && !!surface?.visible;
  const visible = hasContent && (sectionShown || (gameInFront && (mode === "always" || (mode === "start" && startWindow))));
  const scalerShown = !!badge && (installedDll || !!live || !visible);
  if (!host) return null;
  const ghostShown = !!ghostShot && !!running;
  return (
    <>
      {(visible || ghostShown) && <OverGameComposition />}
      {ghostShown && createPortal(
        <>
          <img
            src={ghostShot!.image}
            style={{
              position: "fixed", inset: 0, width: "100%", height: "100%", objectFit: "cover",
              zIndex: 2147483000, pointerEvents: "none", opacity: ghostShot!.opacity,
            }}
          />
          <div style={{
            position: "fixed", bottom: 22, left: "50%", transform: "translateX(-50%)", zIndex: 2147483002,
            pointerEvents: "none", padding: "8px 16px", borderRadius: 999, background: "rgba(10,12,18,.8)",
            color: "#fff", font: "600 13px/16px 'Motiva Sans', Arial, sans-serif", whiteSpace: "nowrap",
            boxShadow: "inset 0 0 0 1px rgba(255,255,255,.16)",
          }}>
            {t("up.compare.ghostHint")}
          </div>
        </>,
        host,
      )}
      {(badge || fgLabel || makoResolutionWarning || makoMultiplier !== null || makoSpatial) && createPortal(
        <div
          style={{
            // Top centre: Steam's performance overlay owns the top-left corner and the Quick Access Menu the right.
            // Opaque on purpose: over a running game the translucent fill showed as bare text on a Steam Deck.
            position: "fixed", top: 10, left: "50%", zIndex: 2147483001, pointerEvents: "none",
            display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
            color: "#eef1f5", whiteSpace: "nowrap",
            font: "600 11px/15px 'Motiva Sans', 'Noto Sans', Arial, sans-serif",
            opacity: visible ? 0.92 : 0, transform: visible ? "translate(-50%, 0)" : "translate(-50%, -6px)",
            transition: "opacity 320ms ease, transform 420ms cubic-bezier(.2,.8,.2,1)",
          }}
        >
          {scalerShown && <div style={{ background: "#15181e", borderRadius: 8, padding: "3px 10px", display: "flex", gap: 8 }}>
            <span>{observedProvider ?? badge!.label}</span>
            {resolution && <span style={{ color: "#9aa3ae", fontVariantNumeric: "tabular-nums" }}>{resolution[0]}p → {resolution[1]}p</span>}
          </div>}
          {makoSpatial && <div style={{ background: "#15181e", borderRadius: 8, padding: "3px 10px", display: "flex", gap: 8 }}>
            <span>Mako</span><span style={{ color: "#9aa3ae", fontVariantNumeric: "tabular-nums" }}>{`${makoSpatial.render.join("×")} → ${makoSpatial.output.join("×")}`}</span>
          </div>}
          {makoResolutionWarning && <div style={{ background: "#15181e", borderRadius: 8, padding: "3px 10px", color: "#ffbe63" }}>
            {t("up.overlay.makoResolution")}
          </div>}
          {makoMultiplier !== null && <div style={{ background: "#15181e", borderRadius: 8, padding: "3px 10px", display: "flex", gap: 8 }}>
            <span>{`Mako ×${makoMultiplier}`}</span><span style={{ color: "#9aa3ae" }}>{t("up.overlay.generating")}</span>
          </div>}
          {fgLabel && <div style={{ background: "#15181e", borderRadius: 8, padding: "3px 10px", display: "flex", gap: 8 }}>
            <span>{fgLabel}</span><span style={{ color: "#9aa3ae" }}>{fgState}</span>
          </div>}
        </div>,
        host,
      )}
    </>
  );
};

/** Mounts covers and the in-game pill for the plugin's lifetime and loads the first overview. */
export function startUpscalerOverlays(): () => void {
  const stopCounterSession = startFpsCounterSession();
  const covers = registerGlobal("PanelDeControlUpscalerCovers", CoverBadges);
  const inGame = registerGlobal("PanelDeControlUpscalerInGame", InGameBadge);
  let stopped = false;
  let retry = 0;
  const load = (attempt: number) => {
    getUpscalersOverview().then((overview) => { if (!stopped) publishOverview(overview); }).catch(() => {
      // Right after Steam starts the backend may not answer yet; covers would stay blank until Escaladores opened.
      if (stopped) return;
      retry = window.setTimeout(() => load(attempt + 1), OVERVIEW_RETRY_MS[Math.min(attempt, OVERVIEW_RETRY_MS.length - 1)]);
    });
  };
  load(0);
  return () => {
    stopped = true;
    stopCounterSession();
    window.clearTimeout(retry);
    inGame();
    covers();
  };
}
