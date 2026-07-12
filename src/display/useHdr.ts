import { useCallback, useEffect, useState } from "react";
import { getHdrState, setHdr, HdrState, HdrPatch } from "../api";

export interface HdrControl {
  state: HdrState | null;
  update: (patch: HdrPatch) => void;
}

/** HDR on/off state. A single toggle → optimistic update, then write immediately. */
export function useHdr(): HdrControl {
  const [state, setState] = useState<HdrState | null>(null);

  useEffect(() => {
    getHdrState().then(setState).catch(() => {});
  }, []);

  const update = useCallback((patch: HdrPatch) => {
    setState((cur) => (cur ? { ...cur, ...patch } : cur)); // optimistic
    setHdr(patch).then(setState).catch(() => {});
  }, []);

  return { state, update };
}
