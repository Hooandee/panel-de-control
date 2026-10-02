import { useEffect, useRef, useState } from "react";

import { BatteryState, FanState, getBatteryState, getFanState, getKioskLive } from "../../../src/api";
import { pushSample } from "./deckMath";

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

export interface LiveFrame {
  fps: number | null;
  playingS: number | null;
  history: readonly number[];
}

/** Gamescope frame rate once a second, with a short history for the pacing line. */
export function useLiveFrame(): LiveFrame {
  const [frame, setFrame] = useState<LiveFrame>({ fps: null, playingS: null, history: [] });
  const history = useRef<number[]>([]);
  useEffect(() => {
    let alive = true;
    const pull = () =>
      getKioskLive()
        .then((live) => {
          if (!alive) return;
          history.current = live.fps == null ? [] : pushSample(history.current, live.fps, FPS_HISTORY);
          setFrame({ fps: live.fps, playingS: live.playing_s, history: history.current });
        })
        .catch(() => {});
    pull();
    const id = window.setInterval(pull, 1000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);
  return frame;
}

export const useFans = () => usePoll<FanState>(getFanState, 2000)[0];
export const useBattery = () => usePoll<BatteryState>(getBatteryState, 15000)[0];

export const artUrl = (appid: string, kind: "hero" | "logo") => `/art/${encodeURIComponent(appid)}/${kind}`;
