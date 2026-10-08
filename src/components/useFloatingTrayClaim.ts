import { useLayoutEffect, useSyncExternalStore } from "react";

const claims = new Set<symbol>();
const listeners = new Set<() => void>();
const getSnapshot = () => claims.size > 0;
const notify = () => listeners.forEach((listener) => listener());

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function useFloatingTrayClaim(active: boolean): void {
  useLayoutEffect(() => {
    if (!active) return;
    const claim = Symbol();
    claims.add(claim);
    notify();
    return () => {
      claims.delete(claim);
      notify();
    };
  }, [active]);
}

export function useFloatingTrayClaimed(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}
