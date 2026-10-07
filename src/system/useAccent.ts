import { useSyncExternalStore } from "react";
import { readString, writeString, onPrefsHealed } from "./pdcStorage";
import { Accent, applyAccentId, getAccent, getAccentId, resolveAccentSelection, subscribeAccent } from "./accentColor";

// Durable persistence (a pdc: key mirrored to the backend). Kept apart from the pure
// accentColor core so its storage chain stays out of theme.ts's import graph.
const KEY = "pdc:accent";

applyAccentId(readString(KEY));
onPrefsHealed(() => applyAccentId(readString(KEY)));

export function setAccent(id: string): void {
  const resolved = resolveAccentSelection(id);
  writeString(KEY, resolved);
  applyAccentId(resolved);
}

export function useAccent(): Accent {
  useSyncExternalStore(subscribeAccent, getAccentId, getAccentId);
  return getAccent();
}
