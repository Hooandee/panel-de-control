import { useCallback, useEffect, useRef, useState } from "react";

import {
  AccessoriesState, getAccessoriesState, NightSchedule, previewAccessoryScene, setAccessoryBrightness,
  setAccessoryAlerts, setAccessoryGameScene, setAccessoryNight, setAccessoryOnSuspend, setAccessoryPower, setAccessoryScene,
} from "../api";
import { decodeFrames, DecodedFrames } from "./pixelFrames";

const POLL_MS = 2500;
const PREVIEW_TTL_MS = 60_000;
const NOT_READY_RETRY_MS = 1500;
const previews = new Map<string, { at: number; value: Promise<DecodedFrames | null> }>();

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

async function fetchPreview(sceneId: string, options: Record<string, unknown>): Promise<DecodedFrames | null> {
  for (let attempt = 0; attempt < 6; attempt += 1) {
    const preview = await previewAccessoryScene(sceneId, options);
    if (!preview || preview.ok === false) return null;
    if (preview.ready !== false || attempt === 5) return decodeFrames(preview);
    await sleep(NOT_READY_RETRY_MS);
  }
  return null;
}

export function loadPreview(sceneId: string, options: Record<string, unknown> = {}): Promise<DecodedFrames | null> {
  const key = `${sceneId}:${JSON.stringify(options)}`;
  const cached = previews.get(key);
  if (cached && Date.now() - cached.at < PREVIEW_TTL_MS) return cached.value;
  const value = fetchPreview(sceneId, options).catch(() => null);
  previews.set(key, { at: Date.now(), value });
  value.then((result) => { if (!result) previews.delete(key); });
  return value;
}

let previewEpoch = 0;

export function forgetPreviews(sceneId?: string): void {
  if (sceneId) {
    for (const key of [...previews.keys()]) if (key.startsWith(`${sceneId}:`)) previews.delete(key);
  } else {
    previews.clear();
  }
  previewEpoch += 1;
  notify();
}

export function usePreviewEpoch(): number {
  useSceneDraft();
  return previewEpoch;
}

export function useAccessories() {
  const [state, setState] = useState<AccessoriesState | null>(null);
  const [failed, setFailed] = useState(false);
  const alive = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const next = await getAccessoriesState();
      if (alive.current && next) setState(next);
    } catch {
      if (alive.current) setFailed(true);
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    void refresh();
    const timer = window.setInterval(() => void refresh(), POLL_MS);
    return () => {
      alive.current = false;
      window.clearInterval(timer);
    };
  }, [refresh]);

  const apply = useCallback(async (call: () => Promise<AccessoriesState>, optimistic?: Partial<AccessoriesState>) => {
    if (optimistic) setState((prev) => (prev ? { ...prev, ...optimistic } : prev));
    try {
      const next = await call();
      if (alive.current && next && next.ok !== false) setState(next);
      return next?.ok !== false;
    } catch {
      return false;
    }
  }, []);

  return {
    state,
    failed,
    refresh,
    chooseScene: (sceneId: string, options: Record<string, unknown> = {}) =>
      apply(() => setAccessoryScene(sceneId, options), { scene: sceneId, options }),
    setBrightness: (percent: number) => apply(() => setAccessoryBrightness(percent), { brightness: percent }),
    setPower: (on: boolean) => apply(() => setAccessoryPower(on), { power: on }),
    setNight: (night: NightSchedule) => apply(() => setAccessoryNight(night), { night }),
    setAlerts: (achievements: boolean) => apply(() => setAccessoryAlerts({ achievements }), { alerts: { achievements } }),
    setGameScene: (sceneId: string | null, options: Record<string, unknown> = {}) =>
      apply(() => setAccessoryGameScene(sceneId, options), { game_scene: sceneId, game_options: options }),
    setOnSuspend: (mode: "off" | "pet") => apply(() => setAccessoryOnSuspend(mode), { on_suspend: mode }),
  };
}

/** The scene being previewed and the open gallery category live outside React: Steam unmounts
 *  the panel under every modal (the city picker, confirmations), which would otherwise lose them. */
export interface SceneDraft {
  id: string;
  options: Record<string, unknown>;
}

let draft: SceneDraft | null = null;
let category: string | null = null;
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((listener) => listener());

export function setSceneDraft(next: SceneDraft | null): void {
  draft = next;
  notify();
}

export function setGalleryCategory(next: string): void {
  category = next;
  notify();
}

export function useSceneDraft(): { draft: SceneDraft | null; category: string | null } {
  const [, force] = useState(0);
  useEffect(() => {
    const listener = () => force((n) => n + 1);
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  }, []);
  return { draft, category };
}
