import { useCallback, useMemo, useSyncExternalStore } from "react";

import { readString, writeStringConfirmed, onPrefsHealed } from "../system/pdcStorage";
import { commitHiddenChange, HIDDEN_KEY, parseHidden } from "./hidden";

// Shared store so the section list and the editor stay in sync: hiding a game in
// the editor updates the list the moment the modal closes. Durable via pdcStorage.
let keys: string[] | null = null;
const subs = new Set<() => void>();
let healHooked = false;

function load(): string[] {
  if (keys === null) keys = parseHidden(readString(HIDDEN_KEY));
  return keys;
}
function publish(next: string[]): void {
  keys = next;
  subs.forEach((cb) => cb());
}
async function commit(next: string[]): Promise<boolean> {
  const previous = load();
  publish(next);
  const result = await commitHiddenChange(previous, next, (value) => writeStringConfirmed(HIDDEN_KEY, value));
  if (!result.saved && keys === next) publish(result.value);
  return result.saved;
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
  isHidden: (instanceKey: string) => boolean;
  hide: (instanceKey: string) => Promise<boolean>;
  unhide: (instanceKey: string) => Promise<boolean>;
}

/** The user's exact hidden library entries, shared + durable across reboots. */
export function useHiddenGames(): HiddenApi {
  const arr = useSyncExternalStore(subscribe, load);
  const hide = useCallback((k: string) => {
    if (load().includes(k)) return Promise.resolve(true);
    return commit([...load(), k]);
  }, []);
  const unhide = useCallback((k: string) => {
    return commit(load().filter((x) => x !== k));
  }, []);
  const set = useMemo(() => new Set(arr), [arr]);
  return { hidden: set, isHidden: (k) => set.has(k), hide, unhide };
}
