import { useSyncExternalStore } from "react";
import { getFanState, FanState } from "../api";
import { pushSample } from "./logic";

const POLL_MS = 1500;
const MAX_SAMPLES = 40;

export interface FanMonitor {
  state: FanState | null;
  /** Rolling RPM history keyed by fan label (stable across set changes). */
  fanHistory: Record<string, number[]>;
}

const EMPTY: FanMonitor = { state: null, fanHistory: {} };

// Ref-counted singleton: one poll shared by every consumer (fanRpm/temps/curve).
class FanStateStore {
  private monitor: FanMonitor = EMPTY;
  private refs = 0;
  private timer: ReturnType<typeof setInterval> | null = null;
  private listeners = new Set<() => void>();

  private tick = (): void => {
    getFanState()
      .then((s) => {
        const prev = this.monitor;
        const fanHistory: Record<string, number[]> = {};
        for (const f of s.fans) {
          const prevBuf = prev.fanHistory[f.label] ?? [];
          fanHistory[f.label] = f.rpm == null ? prevBuf : pushSample(prevBuf, f.rpm, MAX_SAMPLES);
        }
        this.monitor = { state: s, fanHistory };
        this.listeners.forEach((l) => l());
      })
      .catch(() => {});
  };

  subscribe = (cb: () => void): (() => void) => {
    this.listeners.add(cb);
    if (this.refs++ === 0) {
      this.tick();
      this.timer = setInterval(this.tick, POLL_MS);
    }
    return () => {
      this.listeners.delete(cb);
      if (--this.refs === 0 && this.timer) {
        clearInterval(this.timer);
        this.timer = null;
      }
    };
  };

  getSnapshot = (): FanMonitor => this.monitor;
}

const store = new FanStateStore();

export function useFanState(): FanMonitor {
  return useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
}
