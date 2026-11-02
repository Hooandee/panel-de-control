import { findSP } from "@decky/ui";
import { useEffect, useState, type FC } from "react";
import { createPortal } from "react-dom";
import { LuScaling } from "react-icons/lu";

import { getUpscalerLive, getUpscalersOverview } from "../api";
import { useI18n } from "../i18n";
import { registerGlobal } from "../platform/globalComponent";
import { OverGameComposition } from "../platform/overGameComposition";
import { readString, writeString } from "../system/pdcStorage";
import { useRunningGame } from "../tdp/useRunningGame";
import { buildLabel } from "./model";
import type { UpscalersOverview } from "./types";

export type InGameMode = "off" | "start" | "always";
export const IN_GAME_MODES: InGameMode[] = ["off", "start", "always"];

const IN_GAME_KEY = "pdc:upscalers:inGame";
const START_MS = 6000;
const LIVE_POLL_MS = 5000;
const STYLE_ID = "pdc-up-cover-style";
const HOST_ID = "pdc-up-ingame";
const COVER_IMAGE = /\/(?:assets|customimages|apps)\/(\d+)(?:\/|p\.|\.)/;
// Covers only: portrait, header and capsule art or a custom grid image; never icons or the hero backdrop.
const COVER_FILE = /library_600x900|library_capsule|library_header|header|capsule|\/customimages\/\d+p?\./;

interface Badge {
  label: string;
  state: string;
  build: string;
}

let installs: Record<string, Badge> = {};
const listeners = new Set<() => void>();

function emit(): void {
  for (const listener of listeners) listener();
}

/** Publishes what Escaladores knows so covers and the in-game pill follow it without polling. */
export function publishOverview(overview: UpscalersOverview): void {
  const next: Record<string, Badge> = {};
  for (const [appid, install] of Object.entries(overview.installs)) {
    const build = overview.builds.find((b) => b.id === install.build);
    next[appid] = { label: build ? buildLabel(build) : install.build, state: install.status, build: install.build };
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

const COVER_CSS = `
[data-pdc-up]::after {
  content: attr(data-pdc-up);
  position: absolute; top: 6px; left: 6px; z-index: 2;
  padding: 2px 8px; border-radius: 999px;
  font: 700 11px/16px "Motiva Sans", Arial, sans-serif; letter-spacing: .2px;
  color: #fff; background: rgba(12, 14, 20, .78);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, .18), 0 2px 6px rgba(0, 0, 0, .35);
  pointer-events: none;
}
[data-pdc-up-state="active"]::after { box-shadow: inset 0 0 0 1px rgba(126, 224, 160, .7), 0 2px 6px rgba(0, 0, 0, .35); }
[data-pdc-up-state="broken"]::after { color: #ffb454; box-shadow: inset 0 0 0 1px rgba(255, 180, 84, .7), 0 2px 6px rgba(0, 0, 0, .35); }
`;

/** Marks Steam's own cover images; one stylesheet draws the pill, so nothing is re-rendered per cover. */
export const CoverBadges: FC = () => {
  const map = useInstalls();
  useEffect(() => {
    const view = mainWindow();
    const doc = view?.document;
    if (!doc?.body) return;
    let style = doc.getElementById(STYLE_ID);
    if (!style) {
      style = doc.createElement("style");
      style.id = STYLE_ID;
      style.textContent = COVER_CSS;
      doc.head.appendChild(style);
    }
    let pending = 0;
    const mark = () => {
      pending = 0;
      for (const img of Array.from(doc.querySelectorAll<HTMLImageElement>("img[src*='/assets/'], img[src*='/customimages/'], img[src*='/apps/']"))) {
        const holder = img.parentElement;
        if (!holder || !COVER_FILE.test(img.src)) continue;
        const badge = map[img.src.match(COVER_IMAGE)?.[1] ?? ""];
        if (badge) {
          if (holder.getAttribute("data-pdc-up") !== badge.label) holder.setAttribute("data-pdc-up", badge.label);
          if (holder.getAttribute("data-pdc-up-state") !== badge.state) holder.setAttribute("data-pdc-up-state", badge.state);
        } else if (holder.hasAttribute("data-pdc-up")) {
          holder.removeAttribute("data-pdc-up");
          holder.removeAttribute("data-pdc-up-state");
        }
      }
    };
    const schedule = () => {
      if (!pending) pending = view!.setTimeout(mark, 200);
    };
    mark();
    const Observer = (view as Window & typeof globalThis).MutationObserver;
    const observer = new Observer(schedule);
    observer.observe(doc.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["src"] });
    return () => {
      observer.disconnect();
      if (pending) view!.clearTimeout(pending);
      for (const node of Array.from(doc.querySelectorAll("[data-pdc-up]"))) {
        node.removeAttribute("data-pdc-up");
        node.removeAttribute("data-pdc-up-state");
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
  const [mode, setMode] = useState(readInGameMode);
  const [host, setHost] = useState<HTMLDivElement | null>(null);
  const [visible, setVisible] = useState(false);
  const [resolution, setResolution] = useState<[number, number] | null>(null);
  const badge = running ? map[String(running.liveAppid)] : undefined;

  useEffect(() => {
    const update = () => setMode(readInGameMode());
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

  // Appear once OptiScaler has actually created the upscaler, not while the game is still loading.
  useEffect(() => {
    setVisible(false);
    setResolution(null);
    if (!badge || mode === "off" || !running) return;
    let alive = true;
    let hideTimer = 0;
    const poll = window.setInterval(async () => {
      const live = await getUpscalerLive(String(running.liveAppid)).catch(() => null);
      if (!alive) return;
      if (live?.result === "active") {
        window.clearInterval(poll);
        setResolution(live.resolution ? [live.resolution.render[1], live.resolution.output[1]] : null);
        setVisible(true);
        if (mode === "start") hideTimer = window.setTimeout(() => setVisible(false), START_MS);
      }
    }, LIVE_POLL_MS);
    return () => {
      alive = false;
      window.clearInterval(poll);
      window.clearTimeout(hideTimer);
    };
  }, [running?.liveAppid, badge?.build, mode]);

  if (!host || !badge || mode === "off") return null;
  return (
    <>
      {visible && <OverGameComposition />}
      {createPortal(
        <div
          style={{
            position: "fixed", top: 18, left: 18, zIndex: 2147483001, pointerEvents: "none",
            display: "flex", alignItems: "center", gap: 8, padding: "7px 14px 7px 10px", borderRadius: 999,
            background: "rgba(10, 12, 18, .72)", color: "#fff",
            boxShadow: "inset 0 0 0 1px rgba(255,255,255,.16), 0 6px 20px rgba(0,0,0,.4)",
            font: "700 13px/16px 'Motiva Sans', Arial, sans-serif",
            opacity: visible ? 1 : 0, transform: visible ? "translateY(0) scale(1)" : "translateY(-8px) scale(.96)",
            transition: "opacity 320ms ease, transform 420ms cubic-bezier(.2,.8,.2,1)",
          }}
        >
          <span style={{
            display: "inline-flex", width: 22, height: 22, borderRadius: 11, alignItems: "center", justifyContent: "center",
            background: badge.state === "active" ? "rgba(126,224,160,.25)" : "rgba(255,255,255,.12)",
          }}>
            <LuScaling size={13} />
          </span>
          <span style={{ display: "flex", flexDirection: "column" }}>
            {badge.label}
            {resolution && (
              <span style={{ fontSize: 11, fontWeight: 600, opacity: 0.75 }}>
                {t("up.resolution", { render: resolution[0], output: resolution[1] })}
              </span>
            )}
          </span>
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
  getUpscalersOverview().then(publishOverview).catch(() => undefined);
  return () => {
    inGame();
    covers();
  };
}
