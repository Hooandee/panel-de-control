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

const BRIGHTNESS_SETTLE_MS = 250;

export function useAccessories() {
  const [state, setState] = useState<AccessoriesState | null>(null);
  const [failed, setFailed] = useState(false);
  const alive = useRef(true);
  // Every write bumps the generation: a poll or an older write that answers afterwards would
  // otherwise put back the state from before the user's last change.
  const generation = useRef(0);
  const writing = useRef(0);
  const brightnessTimer = useRef<number | undefined>(undefined);

  const refresh = useCallback(async () => {
    const started = generation.current;
    try {
      const next = await getAccessoriesState();
      if (alive.current && next && writing.current === 0 && generation.current === started) {
        setState(next);
        setFailed(false);
      }
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
      window.clearTimeout(brightnessTimer.current);
    };
  }, [refresh]);

  const apply = useCallback(async (call: () => Promise<AccessoriesState>, optimistic?: Partial<AccessoriesState>) => {
    const mine = ++generation.current;
    if (optimistic) setState((prev) => (prev ? { ...prev, ...optimistic } : prev));
    writing.current += 1;
    let ok = false;
    try {
      const next = await call();
      ok = next?.ok !== false;
      if (alive.current && ok && next && generation.current === mine) setState(next);
    } catch {
      ok = false;
    } finally {
      writing.current -= 1;
    }
    if (!ok && generation.current === mine) void refresh();
    return ok;
  }, [refresh]);

  const setBrightness = useCallback((percent: number) => {
    setState((prev) => (prev ? { ...prev, brightness: percent } : prev));
    generation.current += 1;
    window.clearTimeout(brightnessTimer.current);
    brightnessTimer.current = window.setTimeout(() => void apply(() => setAccessoryBrightness(percent), { brightness: percent }),
      BRIGHTNESS_SETTLE_MS);
  }, [apply]);

  return {
    state,
    failed,
    refresh,
    chooseScene: (sceneId: string, options: Record<string, unknown> = {}) =>
      apply(() => setAccessoryScene(sceneId, options), { scene: sceneId, options }),
    setBrightness,
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
