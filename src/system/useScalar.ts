import { useCallback, useEffect, useRef, useState } from "react";
import { ScalarControl, SystemControl } from "./types";
import { acceptEcho, fromPercent, toPercent } from "./logic";
import { displayBrightness } from "./display";
import { systemVolume } from "./audio";

/**
 * Drives a ScalarControl as an integer-percent value. Distinguishes three
 * states so the UI never fakes a reading:
 *  - `supported=false` → the API is absent (subscribe returned no registration).
 *  - `supported && loading` → API present, but no real value has arrived yet
 *    (e.g. volume seeds via an async GetDevices and only emits on change). The
 *    UI must show a placeholder, NOT an interactive slider parked at a fake 0%.
 *  - otherwise → a real value is in `percent`.
 * Writes optimistically on set (the change event corrects if the hardware lands
 * elsewhere).
 *
 * `control` must be a stable module singleton (see display.ts / audio.ts).
 */
export function useScalar(control: ScalarControl): SystemControl {
  const [percent, setPercent] = useState<number | null>(null);
  const [supported, setSupported] = useState(true);
  // The value we last wrote optimistically, and when. Used to reject late echoes
  // from an earlier drag position that would otherwise snap the slider backward.
  const pendingRef = useRef<number | null>(null);
  const lastSetAtRef = useRef(0);

  useEffect(() => {
    let alive = true;
    const unsub = control.subscribe((fraction) => {
      if (!alive) return;
      const echo = toPercent(fraction);
      if (acceptEcho(pendingRef.current, echo, Date.now() - lastSetAtRef.current)) {
        pendingRef.current = null;
        setPercent(echo);
      }
    });
    setSupported(unsub !== null);
    return () => {
      alive = false;
      if (unsub) unsub();
    };
  }, [control]);

  const set = useCallback(
    (p: number) => {
      pendingRef.current = p; // optimistic; ignore echoes until this value confirms
      lastSetAtRef.current = Date.now();
      setPercent(p);
      control.set(fromPercent(p));
    },
    [control],
  );

  return { supported, loading: supported && percent === null, percent: percent ?? 0, set };
}

/** Current screen brightness as an integer percent, with a setter. */
export function useBrightness(): SystemControl {
  return useScalar(displayBrightness);
}

/** Current system volume as an integer percent, with a setter. */
export function useVolume(): SystemControl {
  return useScalar(systemVolume);
}
