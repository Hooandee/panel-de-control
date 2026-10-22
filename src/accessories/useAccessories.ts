import { useCallback, useEffect, useRef, useState } from "react";

import {
  AccessoriesState, getAccessoriesState, NightSchedule, previewAccessoryScene, setAccessoryBrightness,
  setAccessoryAlerts, setAccessoryGameScene, setAccessoryNight, setAccessoryPower, setAccessoryScene,
} from "../api";
import { decodeFrames, DecodedFrames } from "./pixelFrames";

const POLL_MS = 2500;
const previews = new Map<string, Promise<DecodedFrames | null>>();

export function loadPreview(sceneId: string, options: Record<string, unknown> = {}): Promise<DecodedFrames | null> {
  const key = `${sceneId}:${JSON.stringify(options)}`;
  let pending = previews.get(key);
  if (!pending) {
    pending = previewAccessoryScene(sceneId, options)
      .then((preview) => (preview && preview.ok !== false ? decodeFrames(preview) : null))
      .catch(() => null);
    previews.set(key, pending);
    pending.then((value) => { if (!value) previews.delete(key); });
  }
  return pending;
}

export function forgetPreviews(): void {
  previews.clear();
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
    setGameScene: (sceneId: string | null) => apply(() => setAccessoryGameScene(sceneId), { game_scene: sceneId }),
  };
}
