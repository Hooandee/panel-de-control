import { findSP } from "@decky/ui";
import { useEffect, useState, type FC } from "react";
import { createPortal } from "react-dom";

import { getUpscalerLive, getUpscalersOverview } from "../api";
import { useI18n } from "../i18n";
import { registerGlobal } from "../platform/globalComponent";
import { OverGameComposition } from "../platform/overGameComposition";
import { subscribeQamSurface, type QamSurface } from "../platform/qamSurface";
import { readString, writeString } from "../system/pdcStorage";
import { useRunningGame } from "../tdp/useRunningGame";
import { useGameInFront } from "./gameInFront";
import { badgeLabel } from "./model";
import type { UpscalersOverview } from "./types";

export type InGameMode = "off" | "start" | "always";
export const IN_GAME_MODES: InGameMode[] = ["off", "start", "always"];

const IN_GAME_KEY = "pdc:upscalers:inGame";
const START_MS = 6000;
const LIVE_POLL_MS = 5000;
const OVERVIEW_RETRY_MS = [2000, 5000, 15000, 30000, 60000];
const STYLE_ID = "pdc-up-cover-style";
const HOST_ID = "pdc-up-ingame";
const COVER_IMAGE = /\/(?:assets|customimages|apps)\/(\d+)(?:\/|p\.|\.)/;

interface Badge {
  label: string;
  short: string;
  state: string;
  build: string;
}

let installs: Record<string, Badge> = {};
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
    next[appid] = { label: label.full, short: label.short, state: install.status, build: install.build };
  }
  installs = next;
  emit();
}

function useInstalls(): Record<string, Badge> {
  const [value, setValue] = useState(installs);
  useEffect(() => {
    const update = () => setValue(installs);
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
  return parent && tile.contains(parent) ? parent : tile;
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
    tile = parent;
  }
  return tile;
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
  const map = useInstalls();
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
      const marked = new Set<Element>();
      const hosts = new Set<Element>();
      for (const img of Array.from(doc.querySelectorAll<HTMLImageElement>("img[src*='/assets/'], img[src*='/customimages/'], img[src*='/apps/']"))) {
        const appid = appidOf(img.src);
        if (!appid || NOT_TILE.test(img.src)) continue;
        const box = img.getBoundingClientRect();
        if (box.width < 56 || box.height < 40 || box.width > limit) continue;
        const tile = tileOf(img);
        if (!tile || marked.has(tile)) continue;
        if (ICON.test(img.src) && !isRound(tile, view)) continue;
        const badge = map[appid];
        if (!badge) continue;
        marked.add(tile);
        const host = hostOf(img, tile);
        hosts.add(host);
        placeBadge(host, tile, badge, view);
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
  const [resolution, setResolution] = useState<[number, number] | null>(null);
  const badge = running ? map[String(running.liveAppid)] : undefined;

  useEffect(() => {
    const update = () => {
      setMode(readInGameMode());
      setInSection(sectionOpen);
      setGhostShot(ghost);
    };
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

  const [active, setActive] = useState(false);
  const [startWindow, setStartWindow] = useState(false);

  // Appear once OptiScaler has actually created the upscaler, not while the game is still loading.
  useEffect(() => {
    setActive(false);
    setStartWindow(false);
    setResolution(null);
    if (!badge || !running) return;
    let alive = true;
    let hideTimer = 0;
    const poll = window.setInterval(async () => {
      const live = await getUpscalerLive(String(running.liveAppid)).catch(() => null);
      if (!alive || live?.result !== "active") return;
      window.clearInterval(poll);
      setResolution(live.resolution ? [live.resolution.render[1], live.resolution.output[1]] : null);
      setActive(true);
      setStartWindow(true);
      hideTimer = window.setTimeout(() => setStartWindow(false), START_MS);
    }, LIVE_POLL_MS);
    return () => {
      alive = false;
      window.clearInterval(poll);
      window.clearTimeout(hideTimer);
    };
  }, [running?.liveAppid, badge?.build]);

  const sectionShown = inSection && !!surface?.visible;
  const visible = active && (sectionShown || (gameInFront && (mode === "always" || (mode === "start" && startWindow))));
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
      {badge && createPortal(
        <div
          style={{
            // Top centre: Steam's performance overlay owns the top-left corner and the Quick Access Menu the right.
            // Opaque on purpose: over a running game the translucent fill showed as bare text on a Steam Deck.
            position: "fixed", top: 10, left: "50%", zIndex: 2147483001, pointerEvents: "none",
            display: "flex", alignItems: "baseline", gap: 8, padding: "3px 10px", borderRadius: 8,
            background: "#15181e", color: "#eef1f5", whiteSpace: "nowrap",
            font: "600 11px/15px 'Motiva Sans', 'Noto Sans', Arial, sans-serif",
            opacity: visible ? 0.92 : 0, transform: visible ? "translate(-50%, 0)" : "translate(-50%, -6px)",
            transition: "opacity 320ms ease, transform 420ms cubic-bezier(.2,.8,.2,1)",
          }}
        >
          <span>{badge.label}</span>
          {resolution && resolution[0] < resolution[1] && (
            <span style={{ color: "#9aa3ae", fontVariantNumeric: "tabular-nums" }}>{resolution[0]}p → {resolution[1]}p</span>
          )}
        </div>,
        host,
      )}
    </>
  );
};

/** Mounts covers and the in-game pill for the plugin's lifetime and loads the first overview. */
export function startUpscalerOverlays(): () => void {
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
    window.clearTimeout(retry);
    inGame();
    covers();
  };
}
