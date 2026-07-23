import { useSyncExternalStore } from "react";
import { ScalarControl, SystemControl } from "./types";
import { acceptEcho, fromPercent, toPercent } from "./logic";
import { displayBrightness } from "./display";
import { systemVolume } from "./audio";

/**
 * Ref-counted singleton store per ScalarControl: one subscription shared by every
 * consumer (a block in a section AND the same block in a custom view read the same
 * poll — no duplicate registrations). The control's subscribe runs while ≥1 hook is
 * mounted. Three honest states preserved (supported / loading / value); writes are
 * optimistic with late-echo rejection.
 */
class ScalarStore {
  private percent: number | null = null;
  private supported = true;
  private pending: number | null = null;
  private lastSetAt = 0;
  private refs = 0;
  private unsub: (() => void) | null = null;
  private listeners = new Set<() => void>();
  private snap: SystemControl;

  constructor(private control: ScalarControl) {
    this.snap = this.compute();
  }

  private compute(): SystemControl {
    return {
      supported: this.supported,
      loading: this.supported && this.percent === null,
      percent: this.percent ?? 0,
      set: this.set,
    };
  }

  private emit(): void {
    this.snap = this.compute();
    this.listeners.forEach((l) => l());
  }

  private set = (p: number): void => {
    this.pending = p; // optimistic; ignore echoes until this value confirms
    this.lastSetAt = Date.now();
    this.percent = p;
    this.emit();
    this.control.set(fromPercent(p));
  };

  private start(): void {
    const unsub = this.control.subscribe((fraction) => {
      const echo = toPercent(fraction);
      if (acceptEcho(this.pending, echo, Date.now() - this.lastSetAt)) {
        this.pending = null;
        this.percent = echo;
        this.emit();
      }
    });
    this.supported = unsub !== null;
    this.unsub = unsub;
    this.emit();
  }

  subscribe = (cb: () => void): (() => void) => {
    this.listeners.add(cb);
    if (this.refs++ === 0) this.start();
    return () => {
      this.listeners.delete(cb);
      if (--this.refs === 0 && this.unsub) {
        this.unsub();
        this.unsub = null;
      }
    };
  };

  getSnapshot = (): SystemControl => this.snap;
}

const stores = new Map<ScalarControl, ScalarStore>();
function storeFor(control: ScalarControl): ScalarStore {
  let s = stores.get(control);
  if (!s) {
    s = new ScalarStore(control);
    stores.set(control, s);
  }
  return s;
}

/** Drives a ScalarControl as an integer-percent value, sharing one subscription
 *  across all consumers. `control` must be a stable module singleton. */
export function useScalar(control: ScalarControl): SystemControl {
  const store = storeFor(control);
  return useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
}

/** Current screen brightness as an integer percent, with a setter. */
export function useBrightness(): SystemControl {
  return useScalar(displayBrightness);
}

/** Current system volume as an integer percent, with a setter. */
export function useVolume(): SystemControl {
  return useScalar(systemVolume);
}
