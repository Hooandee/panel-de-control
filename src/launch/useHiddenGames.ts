import { useCallback, useMemo, useSyncExternalStore } from "react";

import { readString, writeString, onPrefsHealed } from "../system/pdcStorage";
import { HIDDEN_KEY, parseHidden } from "./hidden";

// Shared store so the section list and the editor stay in sync: hiding a game in
// the editor updates the list the moment the modal closes. Durable via pdcStorage.
let keys: string[] | null = null;
const subs = new Set<() => void>();
let healHooked = false;

function load(): string[] {
  if (keys === null) keys = parseHidden(readString(HIDDEN_KEY));
  return keys;
}
function commit(next: string[]): void {
  keys = next;
  writeString(HIDDEN_KEY, JSON.stringify(next));
  subs.forEach((cb) => cb());
}
function subscribe(cb: () => void): () => void {
  if (!healHooked) {
    healHooked = true;
    onPrefsHealed(() => {
      keys = parseHidden(readString(HIDDEN_KEY));
      subs.forEach((c) => c());
    });
  }
  subs.add(cb);
  return () => subs.delete(cb);
}

export interface HiddenApi {
  hidden: Set<string>;
  isHidden: (stableKey: string) => boolean;
  hide: (stableKey: string) => void;
  unhide: (stableKey: string) => void;
}

/** The user's hidden-games set (stableKeys), shared + durable across reboots. */
export function useHiddenGames(): HiddenApi {
  const arr = useSyncExternalStore(subscribe, load);
  const hide = useCallback((k: string) => {
    if (!load().includes(k)) commit([...load(), k]);
  }, []);
  const unhide = useCallback((k: string) => {
    commit(load().filter((x) => x !== k));
  }, []);
  const set = useMemo(() => new Set(arr), [arr]);
  return { hidden: set, isHidden: (k) => set.has(k), hide, unhide };
}
