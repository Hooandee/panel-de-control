import { useEffect, useState, useSyncExternalStore } from "react";

import { BatteryState, getBatteryState, getKioskLive, getKioskVitals, KioskVitals } from "../../../src/api";
import { pushSample } from "./deckMath";
import { noteRunningGame } from "../runningGame";

/** Poll `read` every `everyMs` while mounted; failures keep the last value. */
export function usePoll<T>(read: () => Promise<T>, everyMs: number): [T | null, (next: T | null) => void] {
  const [value, setValue] = useState<T | null>(null);
  useEffect(() => {
    let alive = true;
    const pull = () => read().then((next) => alive && setValue(next)).catch(() => {});
    pull();
    const id = window.setInterval(pull, everyMs);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [read, everyMs]);
  return [value, setValue];
}

const FPS_HISTORY = 60;
// Matches the overlay's 500 ms refresh so both show the same number at the same moment.
const FRAME_POLL_MS = 500;

export interface LiveFrame {
  fps: number | null;
  playingS: number | null;
  history: readonly number[];
}

// One poller shared by every reader; only the components that show it re-render each second.
let frame: LiveFrame = { fps: null, playingS: null, history: [] };
const frameListeners = new Set<() => void>();
let frameTimer: number | null = null;

function pullFrame(): void {
  getKioskLive()
    .then((live) => {
      const history = live.fps == null ? [] : pushSample(frame.history, live.fps, FPS_HISTORY);
      frame = { fps: live.fps, playingS: live.playing_s, history };
      noteRunningGame(live.appid);
      frameListeners.forEach((listener) => listener());
    })
    .catch(() => {});
}

function subscribeFrame(listener: () => void): () => void {
  frameListeners.add(listener);
  if (frameTimer == null) {
    pullFrame();
    frameTimer = window.setInterval(pullFrame, FRAME_POLL_MS);
  }
  return () => {
    frameListeners.delete(listener);
    if (frameListeners.size === 0 && frameTimer != null) {
      window.clearInterval(frameTimer);
      frameTimer = null;
    }
  };
}

/** Gamescope frame rate once a second, with a short history for the pacing line. */
export const useLiveFrame = (): LiveFrame => useSyncExternalStore(subscribeFrame, () => frame);

export const useBattery = () => usePoll<BatteryState>(getBatteryState, 15000)[0];
export const useVitals = () => usePoll<KioskVitals>(getKioskVitals, 3000)[0];

export const artUrl = (appid: string, kind: "hero" | "logo") => `/art/${encodeURIComponent(appid)}/${kind}`;
