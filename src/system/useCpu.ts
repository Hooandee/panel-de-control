import { useCallback, useEffect, useRef, useState } from "react";
import { CpuState, TdpScope, getCpuState, setActiveCores, setCpuBoost, setCpuFollowGlobal, setSmt } from "../api";
import { useRunningGame } from "../tdp/useRunningGame";

const POLL_MS = 3000; // topology/freq change rarely

export interface CpuController {
  state: CpuState | null;
  scope: TdpScope;
  game: ReturnType<typeof useRunningGame>;
  onScope: (s: TdpScope) => void;
  setSmt: (enabled: boolean) => void;
  setBoost: (enabled: boolean) => void;
  setCores: (count: number) => void;
}

/**
 * Polls get_cpu_state() every ~3 s while mounted. SMT/boost setters are optimistic
 * (flip the toggle immediately) with a pending guard so an in-flight write isn't
 * clobbered by a poll landing mid-flight. Never throws.
 */
export function useCpu(): CpuController {
  const game = useRunningGame();
  const [state, setState] = useState<CpuState | null>(null);
  const [scope, setScope] = useState<TdpScope>("global");
  const pending = useRef(false);
  const appid = game?.appid;

  useEffect(() => {
    let alive = true;
    const tick = () => {
      getCpuState()
        .then((s) => {
          if (alive && !pending.current) setState(s);
        })
        .catch(() => {
          /* keep last values */
        });
    };
    tick();
    const poll = setInterval(tick, POLL_MS);
    return () => {
      alive = false;
      clearInterval(poll);
    };
  }, [appid]);

  // Keep the card's tab in sync with the game's ACTIVE CPU profile (own vs global).
  useEffect(() => {
    if (!state) return;
    setScope(appid && !state.follows_global ? "game" : "global");
  }, [appid, state?.follows_global]);

  const target = scope === "game" ? (appid ?? null) : null;

  // The card's tab IS the control: Global makes the running game follow the global CPU
  // controls; the game tab activates its own. Neither deletes the other.
  const onScope = useCallback(
    (next: TdpScope) => {
      setScope(next);
      if (appid) {
        pending.current = true;
        setCpuFollowGlobal(next === "global", appid)
          .then(setState)
          .catch(() => {})
          .finally(() => { pending.current = false; });
      }
    },
    [appid],
  );

  const apply = useCallback(
    (optimistic: (s: CpuState) => CpuState, rpc: () => Promise<CpuState>) => {
      setState((prev) => (prev ? optimistic(prev) : prev));
      pending.current = true;
      rpc()
        .then((s) => setState(s))
        .catch(() => {
          /* next poll corrects */
        })
        .finally(() => {
          pending.current = false;
        });
    },
    [],
  );

  const doSmt = useCallback(
    (enabled: boolean) =>
      apply((s) => ({ ...s, smt: { ...s.smt, enabled } }), () => setSmt(enabled, scope, target)),
    [apply, scope, target],
  );
  const doBoost = useCallback(
    (enabled: boolean) =>
      apply((s) => ({ ...s, boost: { ...s.boost, enabled } }), () => setCpuBoost(enabled, scope, target)),
    [apply, scope, target],
  );
  const doCores = useCallback(
    (count: number) =>
      apply((s) => ({ ...s, active_cores: count }), () => setActiveCores(count, scope, target)),
    [apply, scope, target],
  );

  return { state, scope, game, onScope, setSmt: doSmt, setBoost: doBoost, setCores: doCores };
}
