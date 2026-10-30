import { useSyncExternalStore } from "react";
import type { AmbientRuntime } from "../steam/runtime";

export type LibraryControl = "toggle" | "progress";
export interface LibraryDock { runtime: AmbientRuntime; element: HTMLDivElement; focus?: LibraryControl | null }
let dock: LibraryDock | null = null;
let activeRegistration: object | null = null;
const listeners = new Set<() => void>();
const publish = () => listeners.forEach((listener) => listener());
export function registerLibraryDock(next: LibraryDock): () => void {
  const registration = {};
  activeRegistration = registration;
  dock = { ...next, focus: null };
  publish();
  return () => {
    if (activeRegistration !== registration) return;
    activeRegistration = null;
    dock = null;
    publish();
  };
}
export function setLibraryDockFocus(element: HTMLDivElement, focus: LibraryControl | null, previous?: LibraryControl): void {
  if (dock?.element !== element || dock.focus === focus || (previous && dock.focus !== previous)) return;
  dock = { ...dock, focus };
  publish();
}
export function useLibraryDock(): LibraryDock | null {
  return useSyncExternalStore((listener) => {
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  }, () => dock);
}
