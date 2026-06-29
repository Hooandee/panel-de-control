import { useCallback, useEffect, useState } from "react";
import { ScalarControl, SystemControl } from "./types";
import { fromPercent, toPercent } from "./logic";

/**
 * Drives a ScalarControl as an integer-percent value. Seeds and tracks the real
 * value from the adapter's change subscription (so the bar reflects hardware
 * buttons / Steam's OSD live), and writes optimistically on set (the change
 * event corrects if the hardware lands elsewhere). Reports supported=false until
 * a real value arrives — never a fake reading.
 *
 * `control` must be a stable module singleton (see display.ts / audio.ts).
 */
export function useScalar(control: ScalarControl): SystemControl {
  const [percent, setPercent] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    const unsub = control.subscribe((fraction) => {
      if (alive) setPercent(toPercent(fraction));
    });
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

  return { supported: percent !== null, percent: percent ?? 0, set };
}
