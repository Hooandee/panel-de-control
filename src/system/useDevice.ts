import { useSyncExternalStore } from "react";
import { getDevice, type DeviceInfo } from "../api";

// Shared device info: fetched once and cached for the whole session (the device
// never changes at runtime). Every consumer reads the same snapshot, so the many
// scattered getDevice() calls collapse to a single RPC. Stable reference until
// the fetch lands → safe for useSyncExternalStore, no render churn.
let cache: DeviceInfo | null = null;
let started = false;
const listeners = new Set<() => void>();

function ensure(): void {
  if (started) return;
  started = true;
  getDevice()
    .then((d) => {
      cache = d;
      listeners.forEach((l) => l());
    })
    .catch(() => {
      started = false; // let a later mount retry if the first read failed
    });
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

const snapshot = (): DeviceInfo | null => cache;

/** The detected device, or null until the first read lands. */
export function useDevice(): DeviceInfo | null {
  ensure();
  return useSyncExternalStore(subscribe, snapshot, snapshot);
}
