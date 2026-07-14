import { useCallback, useEffect, useRef, useState } from "react";
import { CpuState, TdpScope, getCpuState, setActiveCores, setCpuBoost, setCpuFollowGlobal, setSmt } from "../api";
import { useRunningGame } from "../tdp/useRunningGame";
import { useScopeSync } from "../useScopeSync";

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

  // The card's tab reflects the game's active profile and IS the control (shared wiring).
  // The pending guard stops a poll landing mid-write from clobbering the optimistic state.
  const applyFollow = useCallback((f: boolean, a: string) => {
    pending.current = true;
    setCpuFollowGlobal(f, a).then(setState).catch(() => {}).finally(() => { pending.current = false; });
  }, []);
  const { scope, onScope } = useScopeSync(appid, state?.follows_global, applyFollow);

  const target = scope === "game" ? (appid ?? null) : null;

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
