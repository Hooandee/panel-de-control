import { useEffect, useState } from "react";
import { getFanState, FanState } from "../api";
import { pushSample } from "./logic";

const POLL_MS = 1500;
const MAX_SAMPLES = 40;

export interface FanMonitor {
  state: FanState | null;
  /** Rolling RPM history keyed by fan label (stable across set changes). */
  fanHistory: Record<string, number[]>;
  /** Rolling °C history keyed by temp label. */
  tempHistory: Record<string, number[]>;
}

const EMPTY: FanMonitor = { state: null, fanHistory: {}, tempHistory: {} };

/**
 * Polls get_fan_state() every ~1.5 s while mounted (i.e. only while the
 * Ventiladores tab is open) and keeps a rolling sample buffer per fan/temp for
 * the sparklines. History is keyed by label, not array index, so a fan keeps its
 * own buffer even when curation changes the set (e.g. the generic acpi_fan is
 * dropped once a vendor chip appears) — no cross-contaminated graphs. One state
 * update per tick (single render). Never throws.
 */
export function useFanState(): FanMonitor {
  const [monitor, setMonitor] = useState<FanMonitor>(EMPTY);

  useEffect(() => {
    let alive = true;
    const tick = () => {
      getFanState()
        .then((s) => {
          if (!alive) return;
          setMonitor((prev) => {
            const fanHistory: Record<string, number[]> = {};
            for (const f of s.fans) {
              fanHistory[f.label] = pushSample(prev.fanHistory[f.label] ?? [], f.rpm, MAX_SAMPLES);
            }
            const tempHistory: Record<string, number[]> = {};
            for (const t of s.temps) {
              tempHistory[t.label] = pushSample(prev.tempHistory[t.label] ?? [], t.celsius, MAX_SAMPLES);
            }
            return { state: s, fanHistory, tempHistory };
          });
        })
        .catch(() => {
          /* keep last values */
        });
    };
    tick();
    const timer = setInterval(tick, POLL_MS);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  return monitor;
}
