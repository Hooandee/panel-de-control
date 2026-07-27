import { useSyncExternalStore } from "react";
import { readString, writeString, onPrefsHealed } from "./pdcStorage";
import { Accent, applyAccentId, getAccentId, resolveAccent, subscribeAccent } from "./accentColor";

// Durable persistence (a pdc: key mirrored to the backend). Kept apart from the pure
// accentColor core so its storage chain stays out of theme.ts's import graph.
const KEY = "pdc:accent";

applyAccentId(resolveAccent(readString(KEY)).id);
onPrefsHealed(() => applyAccentId(resolveAccent(readString(KEY)).id));

export function setAccent(id: string): void {
  const resolved = resolveAccent(id).id;
  writeString(KEY, resolved);
  applyAccentId(resolved);
}

export function useAccent(): Accent {
  const id = useSyncExternalStore(subscribeAccent, getAccentId, getAccentId);
  return resolveAccent(id);
}
