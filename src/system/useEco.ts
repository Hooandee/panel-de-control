import { useEffect, useRef, useState } from "react";
import { EcoState, getEcoState, setEco } from "../api";
import { setEcoActiveHint } from "./ecoAmbient";

const POLL_MS = 3000; // keep the toggle in sync when another card's manual change clears eco

export interface EcoController {
  state: EcoState | null;
  /** Toggle download mode. `currentBrightnessPct` is snapshotted as the wake level. */
  toggle: (enabled: boolean, currentBrightnessPct: number) => void;
}

/**
 * Drives the download-mode card. The persistent ambient controller
 * (ecoAmbient) actually owns the screen brightness; here we just flip the mode
 * and hand it the wake level for an instant response, with the RPC as the
 * source of truth.
 */
export function useEco(): EcoController {
  const [state, setState] = useState<EcoState | null>(null);
  // True while an optimistic toggle write is in flight, so a poll landing mid-flight
  // doesn't clobber it (same pattern as useCpu/useBattery).
  const pending = useRef(false);

  useEffect(() => {
    let alive = true;
    const tick = () => {
      getEcoState()
        .then((s) => {
          if (alive && !pending.current) setState(s);
        })
        .catch(() => {
          /* backend not ready */
        });
    };
    tick();
    const poll = setInterval(tick, POLL_MS);
    return () => {
      alive = false;
      clearInterval(poll);
    };
  }, []);

  const toggle = (enabled: boolean, currentBrightnessPct: number) => {
    const wake = enabled ? currentBrightnessPct : (state?.wake_brightness ?? currentBrightnessPct);
    setEcoActiveHint(enabled, wake); // instant (persistent controller)
    setState((prev) => (prev ? { ...prev, enabled } : prev)); // optimistic
    pending.current = true;
    setEco(enabled, currentBrightnessPct)
      .then(setState) // RPC is the source of truth; the hint already drove brightness
      .catch(() => {
        /* next poll corrects */
      })
      .finally(() => {
        pending.current = false;
      });
  };

  return { state, toggle };
}
