import { useEffect, useSyncExternalStore } from "react";
import { getDevice, type DeviceInfo } from "../api";

interface DeviceSnapshot {
  device: DeviceInfo | null;
  failed: boolean;
}

let state: DeviceSnapshot = { device: null, failed: false };
let started = false;
const listeners = new Set<() => void>();

function publish(next: DeviceSnapshot): void {
  state = next;
  listeners.forEach((listener) => listener());
}

export function ensureDevice(): void {
  if (started) return;
  started = true;
  getDevice()
    .then((device) => publish({ device, failed: false }))
    .catch(() => {
      publish({ device: null, failed: true });
      started = false;
    });
}

export function subscribeDevice(cb: () => void): () => void {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

export function getDeviceSnapshot(): DeviceInfo | null {
  return state.device;
}

export function useDevice(): DeviceInfo | null {
  const device = useSyncExternalStore(subscribeDevice, getDeviceSnapshot, getDeviceSnapshot);
  useEffect(ensureDevice, []);
  return device;
}

export function useDeviceState(): DeviceSnapshot {
  const snapshot = useSyncExternalStore(subscribeDevice, () => state, () => state);
  useEffect(ensureDevice, []);
  return snapshot;
}
