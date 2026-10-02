import { useEffect, useRef, useState } from "react";

import {
  BatteryState,
  FanState,
  getBatteryState,
  getFanState,
  getKioskGame,
  getPowerDraw,
  getTdpState,
  PowerDraw,
  TdpState,
} from "../../../src/api";

export interface Live {
  power: PowerDraw | null;
  battery: BatteryState | null;
  fans: FanState | null;
  tdp: TdpState | null;
}

const EVERY: Array<[keyof Live, () => Promise<unknown>, number]> = [
  ["power", getPowerDraw, 2000],
  ["fans", getFanState, 4000],
  ["battery", getBatteryState, 15000],
  ["tdp", getTdpState, 5000],
];

export function useLive(): Live {
  const [live, setLive] = useState<Live>({ power: null, battery: null, fans: null, tdp: null });
  useEffect(() => {
    let alive = true;
    const timers = EVERY.map(([key, read, ms]) => {
      const pull = () =>
        read()
          .then((value) => alive && setLive((prev) => ({ ...prev, [key]: value })))
          .catch(() => {});
      pull();
      return window.setInterval(pull, ms);
    });
    return () => {
      alive = false;
      timers.forEach((id) => window.clearInterval(id));
    };
  }, []);
  return live;
}

export interface RunningGame {
  appid: string;
  name: string | null;
  since: number;
}

/** The game Panel is applying profiles for, with when this screen first saw it. */
export function useRunningGame(appid: string | null | undefined): RunningGame | null {
  const [game, setGame] = useState<RunningGame | null>(null);
  const seen = useRef<{ appid: string; since: number } | null>(null);
  useEffect(() => {
    if (!appid) {
      seen.current = null;
      setGame(null);
      return;
    }
    if (seen.current?.appid !== appid) seen.current = { appid, since: Date.now() };
    const since = seen.current.since;
    let alive = true;
    setGame({ appid, name: null, since });
    getKioskGame(appid)
      .then((found) => alive && setGame({ appid, name: found.name, since }))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [appid]);
  return game;
}

export const artUrl = (appid: string, kind: "hero" | "logo") => `/art/${encodeURIComponent(appid)}/${kind}`;
