import { getBatteryState } from "../api";

export interface PowerSnapshot {
  battery: { percent: number; charging: boolean } | null;
}

export interface PowerPort {
  subscribe(listener: (snapshot: PowerSnapshot) => void): () => void;
}

const POLL_MS = 60_000;

type BatteryReader = typeof getBatteryState;

/** Battery for policies that care. No battery or an unreadable one is reported as null, never guessed. */
export function createPowerPort(read: BatteryReader = getBatteryState): PowerPort {
  return {
    subscribe(listener) {
      let alive = true;
      const tick = async () => {
        let snapshot: PowerSnapshot = { battery: null };
        try {
          const { battery } = await read();
          if (battery.present && typeof battery.percent === "number") {
            const charging = battery.ac_online === true || battery.status === "Charging" || battery.status === "Full";
            snapshot = { battery: { percent: battery.percent, charging } };
          }
        } catch {
          snapshot = { battery: null };
        }
        if (alive) listener(snapshot);
      };
      void tick();
      const timer = setInterval(() => void tick(), POLL_MS);
      return () => {
        alive = false;
        clearInterval(timer);
      };
    },
  };
}
