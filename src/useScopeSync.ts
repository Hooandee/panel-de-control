import { useCallback, useEffect, useState } from "react";
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
  applyFollowGlobal: (follow: boolean, appid: string) => void,
): { scope: Scope; onScope: (next: Scope) => void } {
  const [scope, setScope] = useState<Scope>("global");

  useEffect(() => {
    if (followsGlobal === undefined) return; // state not loaded yet
    setScope(scopeFor(appid, followsGlobal));
  }, [appid, followsGlobal]);

  const onScope = useCallback(
    (next: Scope) => {
      setScope(next);
      if (appid) applyFollowGlobal(next === "global", appid);
    },
    [appid, applyFollowGlobal],
  );

  return { scope, onScope };
}
