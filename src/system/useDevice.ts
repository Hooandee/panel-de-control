import { useSyncExternalStore } from "react";
import { getDevice, type DeviceInfo } from "../api";

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
      started = false;
    });
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

const snapshot = (): DeviceInfo | null => cache;

export function useDevice(): DeviceInfo | null {
  ensure();
  return useSyncExternalStore(subscribe, snapshot, snapshot);
}
