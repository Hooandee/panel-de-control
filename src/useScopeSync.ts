import { useCallback, useEffect, useRef, useState } from "react";
import type { Scope } from "./api";
import { scopeFor } from "./scope";

/**
 * Shared global/per-game scope-tab wiring, identical across every per-game section
 * (Potencia, Ventiladores, Pantalla, CPU, Mandos). The tab reflects the running game's
 * active profile AND is the control: picking one drives follow_global via the section's
 * own RPC (passed as `applyFollowGlobal`), never deleting the other side.
 *
 * `followsGlobal` is undefined until the section's state has loaded — the tab is not
 * forced to global before then (matches the old per-section `if (!state) return`).
 */
export function useScopeSync(
  appid: string | null | undefined,
  followsGlobal: boolean | undefined,
  applyFollowGlobal: (
    follow: boolean,
    appid: string,
  ) => boolean | void | Promise<boolean | void>,
): { scope: Scope; onScope: (next: Scope) => void } {
  const [scope, setScope] = useState<Scope>("global");
  const actionEpoch = useRef(0);

  useEffect(() => {
    ++actionEpoch.current;
  }, [appid]);

  useEffect(() => {
    if (followsGlobal === undefined) return; // state not loaded yet
    setScope(scopeFor(appid, followsGlobal));
  }, [appid, followsGlobal]);

  const onScope = useCallback(
    (next: Scope) => {
      const previous = scope;
      const epoch = ++actionEpoch.current;
      setScope(next);
      if (!appid) return;
      const rollback = () => {
        if (epoch === actionEpoch.current) setScope(previous);
      };
      try {
        const result = applyFollowGlobal(next === "global", appid);
        if (result instanceof Promise) {
          result.then((ok) => {
            if (ok === false) rollback();
          }).catch(rollback);
        } else if (result === false) {
          rollback();
        }
      } catch {
        rollback();
      }
    },
    [appid, applyFollowGlobal, scope],
  );

  return { scope, onScope };
}
