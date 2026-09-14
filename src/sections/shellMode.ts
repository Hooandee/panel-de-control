import { useSyncExternalStore } from "react";
import { readString, writeString } from "../system/pdcStorage";

export type ShellMode = "home" | "detail" | "tabs";

const KEY = "pdc:shellMode";
const listeners = new Set<() => void>();
let cache: ShellMode | null | undefined;

function parse(value: string | null): ShellMode | null {
  return value === "home" || value === "detail" || value === "tabs" ? value : null;
}

export function getShellMode(): ShellMode | null {
  if (cache === undefined) cache = parse(readString(KEY));
  return cache;
}

export function setShellMode(mode: ShellMode): void {
  if (getShellMode() === mode) return;
  cache = mode;
  writeString(KEY, mode);
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useShellMode(): ShellMode | null {
  return useSyncExternalStore(subscribe, getShellMode, getShellMode);
}
