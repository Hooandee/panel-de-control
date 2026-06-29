import { useCallback, useEffect, useState } from "react";
import { ScalarControl, SystemControl } from "./types";
import { fromPercent, toPercent } from "./logic";
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

  useEffect(() => {
    let alive = true;
    const unsub = control.subscribe((fraction) => {
      if (alive) setPercent(toPercent(fraction));
    });
    setSupported(unsub !== null);
    return () => {
      alive = false;
      if (unsub) unsub();
    };
  }, [control]);

  const set = useCallback(
    (p: number) => {
      setPercent(p); // optimistic; the change event confirms/corrects
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
