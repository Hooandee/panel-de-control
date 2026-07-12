import { useCallback, useEffect, useRef, useState } from "react";
import { getNightState, setNight, NightState, NightPatch } from "../api";

export interface NightControl {
  state: NightState | null;
  update: (patch: NightPatch) => void;
}

/** Night-mode state. Fetches once on mount; polls only while scheduled (a schedule edge
 *  can flip `active` on its own). Writes are optimistic + debounced, merging rapid edits
 *  so one doesn't drop another; the `writing` guard keeps a poll from overwriting an
 *  edit that hasn't been saved yet. */
export function useNight(): NightControl {
  const [state, setState] = useState<NightState | null>(null);
  const commit = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pending = useRef<NightPatch>({});
  const writing = useRef(false);

  useEffect(() => {
    getNightState().then(setState).catch(() => {});
    return () => {
      if (commit.current) clearTimeout(commit.current);
    };
  }, []);

  const scheduled = !!(state?.enabled && state?.schedule_enabled);
  useEffect(() => {
    if (!scheduled) return;
    const iv = setInterval(() => {
      if (writing.current) return; // don't clobber an in-flight edit
      getNightState().then((s) => { if (!writing.current) setState(s); }).catch(() => {});
    }, 30000);
    return () => clearInterval(iv);
  }, [scheduled]);

  const update = useCallback((patch: NightPatch) => {
    setState((cur) => (cur ? { ...cur, ...patch } : cur)); // optimistic
    pending.current = { ...pending.current, ...patch };
    writing.current = true;
    if (commit.current) clearTimeout(commit.current);
    commit.current = setTimeout(() => {
      const p = pending.current;
      pending.current = {};
      setNight(p)
        .then((s) => { writing.current = false; setState(s); })
        .catch(() => { writing.current = false; });
    }, 200);
  }, []);

  return { state, update };
}
