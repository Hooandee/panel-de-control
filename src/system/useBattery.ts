import { useCallback, useEffect, useRef, useState } from "react";
import { BatteryState, ChargeLimit, getBatteryState, setChargeLimit } from "../api";

const POLL_MS = 3000; // battery changes slowly
const DEBOUNCE_MS = 250; // coalesce slider drags before writing

export interface BatteryController {
  /** null until the first read lands (show a spinner, never a fake 0%). */
  state: BatteryState | null;
  /** Enable/disable + set threshold. Optimistic; the next poll confirms. */
  setLimit: (enabled: boolean, percent: number) => void;
}

/**
 * Polls get_battery_state() every ~3 s while mounted (only while the Sistema tab
 * is open). The charge-limit setter is optimistic + debounced so dragging the
 * threshold slider stays smooth and doesn't spam the backend. Never throws.
 */
export function useBattery(): BatteryController {
  const [state, setState] = useState<BatteryState | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // True while an optimistic charge-limit write is in flight: a poll landing in
  // this window must not clobber the optimistic charge_limit with the stale
  // backend value (which would visibly bounce the toggle/slider for a frame).
  const pending = useRef(false);

  useEffect(() => {
    let alive = true;
    const tick = () => {
      getBatteryState()
        .then((s) => {
          if (!alive) return;
          // keep the live battery info, but preserve an in-flight limit choice
          setState((prev) =>
            pending.current && prev ? { ...s, charge_limit: prev.charge_limit } : s,
          );
        })
        .catch(() => {
          /* keep last values */
        });
    };
    tick();
    const poll = setInterval(tick, POLL_MS);
    return () => {
      alive = false;
      clearInterval(poll);
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  const setLimit = useCallback((enabled: boolean, percent: number) => {
    // optimistic: reflect the choice immediately
    setState((prev) =>
      prev ? { ...prev, charge_limit: { ...prev.charge_limit, enabled, percent } } : prev,
    );
    pending.current = true;
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      setChargeLimit(enabled, percent)
        .then((cl: ChargeLimit) => {
          setState((prev) => (prev ? { ...prev, charge_limit: cl } : prev));
        })
        .catch(() => {
          /* next poll corrects */
        })
        .finally(() => {
          pending.current = false;
        });
    }, DEBOUNCE_MS);
  }, []);

  return { state, setLimit };
}
