import { useEffect, useState } from "react";

import { BatteryState, FanState, getBatteryState, getFanState } from "../../../src/api";

export interface Live {
  battery: BatteryState | null;
  fans: FanState | null;
}

const EVERY: Array<[keyof Live, () => Promise<unknown>, number]> = [
  ["fans", getFanState, 2000],
  ["battery", getBatteryState, 15000],
];

export function useLive(): Live {
  const [live, setLive] = useState<Live>({ battery: null, fans: null });
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

export const artUrl = (appid: string, kind: "hero" | "logo") => `/art/${encodeURIComponent(appid)}/${kind}`;
