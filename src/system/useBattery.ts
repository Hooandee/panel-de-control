import { useCallback, useEffect, useRef, useState } from "react";
import {
  BatteryState,
  ChargeLimit,
  getBatteryState,
  setChargeLimit,
  setChargeLimitFullOnce,
} from "../api";

const POLL_MS = 3000; // battery changes slowly
const DEBOUNCE_MS = 250; // coalesce slider drags before writing

export interface BatteryController {
  /** null until the first read lands (show a spinner, never a fake 0%). */
  state: BatteryState | null;
  /** Enable/disable + set threshold. Optimistic; the next poll confirms. */
  setLimit: (enabled: boolean, percent: number) => void;
  setFullChargeOnce: (enabled: boolean) => void;
}

/**
 * Polls get_battery_state() every ~3 s while mounted (only while the Sistema tab
 * is open). The charge-limit setter is optimistic + debounced so dragging the
 * threshold slider stays smooth and doesn't spam the backend. Never throws.
 */
export function useBattery(): BatteryController {
  const [state, setState] = useState<BatteryState | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingLimit = useRef<{
    enabled: boolean;
    percent: number;
    request: number;
  } | null>(null);
  const mutationQueue = useRef<Promise<void>>(Promise.resolve());
  // True while an optimistic charge-limit write is in flight: a poll landing in
  // this window must not clobber the optimistic charge_limit with the stale
  // backend value (which would visibly bounce the toggle/slider for a frame).
  const pending = useRef(false);
  const mutation = useRef(0);

  const enqueueMutation = useCallback(<T,>(operation: () => Promise<T>): Promise<T> => {
    const queued = mutationQueue.current.then(operation, operation);
    mutationQueue.current = queued.then(() => undefined, () => undefined);
    return queued;
  }, []);

  const commitMutation = useCallback((
    request: number,
    operation: () => Promise<ChargeLimit>,
  ) => {
    enqueueMutation(operation)
      .then((chargeLimit) => {
        if (mutation.current !== request) return;
        setState((prev) => (prev ? { ...prev, charge_limit: chargeLimit } : prev));
      })
      .catch(() => {
        /* next poll corrects */
      })
      .finally(() => {
        if (mutation.current === request) pending.current = false;
      });
  }, [enqueueMutation]);

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
      mutation.current += 1;
      clearInterval(poll);
      if (timer.current) clearTimeout(timer.current);
      pendingLimit.current = null;
    };
  }, []);

  const setLimit = useCallback((enabled: boolean, percent: number) => {
    const request = ++mutation.current;
    setState((prev) =>
      prev ? {
        ...prev,
        charge_limit: {
          ...prev.charge_limit,
          enabled,
          percent,
          full_charge_once: {
            ...prev.charge_limit.full_charge_once,
            available: enabled && prev.charge_limit.full_charge_once.available,
            active: false,
            status: "inactive",
            expires_at: null,
          },
        },
      } : prev,
    );
    pending.current = true;
    if (timer.current) clearTimeout(timer.current);
    pendingLimit.current = { enabled, percent, request };
    timer.current = setTimeout(() => {
      const intent = pendingLimit.current;
      pendingLimit.current = null;
      timer.current = null;
      if (!intent) return;
      commitMutation(
        intent.request,
        () => setChargeLimit(intent.enabled, intent.percent),
      );
    }, DEBOUNCE_MS);
  }, [commitMutation]);

  const setFullChargeOnce = useCallback((enabled: boolean) => {
    const request = ++mutation.current;
    if (timer.current) {
      clearTimeout(timer.current);
      timer.current = null;
    }
    const limitIntent = pendingLimit.current;
    pendingLimit.current = null;
    pending.current = true;
    setState((prev) => {
      if (!prev) return prev;
      const active = enabled
        && prev.charge_limit.enabled
        && prev.charge_limit.full_charge_once.available;
      return {
        ...prev,
        charge_limit: {
          ...prev.charge_limit,
          full_charge_once: {
            ...prev.charge_limit.full_charge_once,
            active,
            status: active ? "pending" : "inactive",
            expires_at: enabled ? prev.charge_limit.full_charge_once.expires_at : null,
          },
        },
      };
    });
    commitMutation(request, async () => {
      if (limitIntent) await setChargeLimit(limitIntent.enabled, limitIntent.percent);
      return setChargeLimitFullOnce(enabled);
    });
  }, [commitMutation]);

  return { state, setLimit, setFullChargeOnce };
}
