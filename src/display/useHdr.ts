import { useCallback, useEffect, useState } from "react";
import { getHdrState, setHdr, HdrState, HdrPatch, Scope } from "../api";

export interface HdrControl {
  state: HdrState | null;
  update: (patch: HdrPatch) => void;
}

/** HDR on/off state, per-game via the shared color scope. A toggle → optimistic
 *  update, then write to the active scope. Re-fetches when the scope changes. */
export function useHdr(scope: Scope, appid: string | null): HdrControl {
  const [state, setState] = useState<HdrState | null>(null);
  const target = scope === "game" ? appid : null;

  useEffect(() => {
    getHdrState().then(setState).catch(() => {});
  }, [scope, appid]);

  const update = useCallback((patch: HdrPatch) => {
    setState((cur) => (cur ? { ...cur, ...patch } : cur)); // optimistic
    setHdr(patch, scope, target).then(setState).catch(() => {});
  }, [scope, target]);

  return { state, update };
}
